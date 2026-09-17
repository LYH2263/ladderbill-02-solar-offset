import json
import sqlite3

from fastapi import HTTPException

from app.db import connect
from app.engines.peak_compare import compare_plain_vs_peak
from app.engines.tier_progressive import calc_bill
from app.modules.solar_offset import calc_bill_with_offset
from app.repositories import accounts as accounts_repo
from app.repositories import readings as readings_repo
from app.repositories import runs as runs_repo
from app.repositories import settings as settings_repo
from app.repositories import solar_offsets as solar_repo
from app.repositories import tiers as tiers_repo


class BillingService:
    def __init__(self):
        self._conn = connect()

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def list_accounts(self):
        return accounts_repo.list_all(self._conn)

    def get_account(self, account_id: int):
        return accounts_repo.get(self._conn, account_id)

    def list_tiers(self):
        return tiers_repo.list_ordered(self._conn)

    def list_readings(self):
        return readings_repo.list_all(self._conn)

    def readings_for_account(self, account_id: int):
        return readings_repo.for_account(self._conn, account_id)

    def settings_map(self):
        return settings_repo.get_map(self._conn)

    def run_bill(self, kwh: float, peak: bool, account_id: int | None, persist: bool,
                 period: str | None = None):
        tiers = tiers_repo.as_calc_rows(self._conn)
        pf = settings_repo.peak_factor(self._conn)
        factor = pf if peak else 1.0

        # A billing period engages the solar-offset pipeline (deduct -> tier -> factor).
        if period is not None:
            account = self._require_account(account_id)
            offset_row = solar_repo.get_active(self._conn, account["id"], period)
            offset_kwh = float(offset_row["offset_kwh"]) if offset_row else 0.0
            result = calc_bill_with_offset(kwh, offset_kwh, tiers, factor)
            run_id = None
            if persist:
                run_id = runs_repo.insert(
                    self._conn,
                    "solar_bill",
                    {
                        "account_id": account["id"],
                        "period": period,
                        "gross_kwh": kwh,
                        "offset_kwh": result["offset_kwh"],
                        "net_kwh": result["net_kwh"],
                        "peak": peak,
                        "offset_id": offset_row["id"] if offset_row else None,
                    },
                    result,
                    account["id"],
                )
            return {"run_id": run_id, **result}

        result = calc_bill(kwh, tiers, factor)
        run_id = None
        if persist:
            run_id = runs_repo.insert(
                self._conn,
                "bill",
                {"kwh": kwh, "peak": peak, "account_id": account_id},
                result,
                account_id,
            )
        return {"run_id": run_id, **result}

    def run_compare(self, kwh: float, persist: bool):
        tiers = tiers_repo.as_calc_rows(self._conn)
        pf = settings_repo.peak_factor(self._conn)
        result = compare_plain_vs_peak(kwh, tiers, pf)
        run_id = None
        if persist:
            run_id = runs_repo.insert(self._conn, "compare", {"kwh": kwh}, result, None)
        return {"run_id": run_id, **result}

    def _require_account(self, account_id: int | None) -> dict:
        if account_id is None:
            raise HTTPException(422, "account_id is required")
        account = accounts_repo.get(self._conn, account_id)
        if not account:
            raise HTTPException(404, "account not found")
        return account

    # ---- solar offsets -------------------------------------------------

    def list_offsets(self, account_id: int):
        self._require_account(account_id)
        return solar_repo.list_for_account(self._conn, account_id)

    def create_offset(self, *, account_id: int, period: str, offset_kwh: float,
                      source_note: str | None, entered_by: str | None) -> dict:
        self._require_account(account_id)
        existing = solar_repo.get_active(self._conn, account_id, period)
        if existing:
            raise HTTPException(
                409,
                f"active offset v{existing['version']} already exists for this period; "
                "correct it with an explicit base_version",
            )
        try:
            return solar_repo.create(
                self._conn,
                account_id=account_id,
                period=period,
                offset_kwh=offset_kwh,
                source_note=source_note,
                entered_by=entered_by,
            )
        except sqlite3.IntegrityError:
            # Race against a concurrent insert of the same active (account, period).
            raise HTTPException(409, "an active offset for this period already exists")

    def correct_offset(self, account_id: int, period: str, *, base_version: int,
                       offset_kwh: float, source_note: str | None,
                       entered_by: str | None) -> dict:
        self._require_account(account_id)
        base = solar_repo.get_active(self._conn, account_id, period)
        if not base:
            raise HTTPException(404, "no active offset for this account and period to correct")
        if base["version"] != base_version:
            raise HTTPException(
                409,
                f"base_version {base_version} is stale; current active version is "
                f"v{base['version']}",
            )
        return solar_repo.correct(
            self._conn,
            base=base,
            offset_kwh=offset_kwh,
            source_note=source_note,
            entered_by=entered_by,
        )

    def void_offset(self, account_id: int, period: str, base_version: int) -> dict:
        self._require_account(account_id)
        base = solar_repo.get_active(self._conn, account_id, period)
        if not base or base["version"] != base_version:
            raise HTTPException(404, "no active offset matching that account, period and version")
        solar_repo.deactivate(self._conn, base["id"])
        return {"voided_id": base["id"], "account_id": account_id, "period": period,
                "version": base_version}

    def preview_offset_bill(self, *, account_id: int, period: str, gross_kwh: float,
                            peak: bool) -> dict:
        account = self._require_account(account_id)
        tiers = tiers_repo.as_calc_rows(self._conn)
        pf = settings_repo.peak_factor(self._conn)
        factor = pf if peak else 1.0
        offset_row = solar_repo.get_active(self._conn, account["id"], period)
        offset_kwh = float(offset_row["offset_kwh"]) if offset_row else 0.0
        result = calc_bill_with_offset(gross_kwh, offset_kwh, tiers, factor)
        # Preview only: never writes an offset row nor a calc_run.
        return {
            "run_id": None,
            "period": period,
            "has_active_offset": bool(offset_row),
            "offset_version": offset_row["version"] if offset_row else None,
            **result,
        }

    def list_history(self, limit: int = 50):
        return runs_repo.list_recent(self._conn, limit)

    def get_run(self, run_id: int):
        return runs_repo.get(self._conn, run_id)

    def dashboard_stats(self):
        accounts = accounts_repo.list_all(self._conn)
        readings = readings_repo.list_all(self._conn)
        clean = [a for a in accounts if "种子" not in a.get("name", "")]
        dirty = [a for a in accounts if "种子" in a.get("name", "")]
        return {
            "account_count": len(accounts),
            "reading_count": len(readings),
            "clean_accounts": len(clean),
            "dirty_accounts": len(dirty),
            "recent_runs": len(runs_repo.list_recent(self._conn, 5)),
        }
