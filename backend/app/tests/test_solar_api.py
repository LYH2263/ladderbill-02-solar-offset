import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    # Redirect the SQLite file before the app's startup seed runs.
    from app import db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test_solar.db", raising=True)
    from app.main import app
    with TestClient(app) as c:
        yield c


ACCOUNT = 1  # seeded 张家
PERIOD = "2026-09"


def _create(client, period=PERIOD, kwh=200, note="屋顶光伏", who="抄表员甲"):
    return client.post(
        f"/api/accounts/{ACCOUNT}/solar-offsets",
        json={"period": period, "offset_kwh": kwh, "source_note": note, "entered_by": who},
    )


def test_create_offset_persists_and_lists(client):
    r = _create(client)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["version"] == 1
    assert body["is_active"] == 1
    assert body["offset_kwh"] == 200
    assert body["entered_by"] == "抄表员甲"

    rows = client.get(f"/api/accounts/{ACCOUNT}/solar-offsets").json()["items"]
    assert len(rows) == 1 and rows[0]["period"] == PERIOD


def test_unknown_account_is_404(client):
    r = client.post(
        "/api/accounts/999/solar-offsets",
        json={"period": PERIOD, "offset_kwh": 10},
    )
    assert r.status_code == 404


def test_negative_kwh_and_bad_period_are_422(client):
    r = client.post(
        f"/api/accounts/{ACCOUNT}/solar-offsets",
        json={"period": PERIOD, "offset_kwh": -5},
    )
    assert r.status_code == 422
    r = client.post(
        f"/api/accounts/{ACCOUNT}/solar-offsets",
        json={"period": "2026/09", "offset_kwh": 5},
    )
    assert r.status_code == 422


def test_no_two_parallel_active_records_same_account_period(client):
    assert _create(client, kwh=100).status_code == 201
    dup = _create(client, kwh=120)
    assert dup.status_code == 409
    rows = client.get(f"/api/accounts/{ACCOUNT}/solar-offsets").json()["items"]
    assert len(rows) == 1


def test_same_period_allowed_for_different_accounts(client):
    assert _create(client).status_code == 201
    r = client.post(
        f"/api/accounts/2/solar-offsets",
        json={"period": PERIOD, "offset_kwh": 50},
    )
    assert r.status_code == 201


def test_correction_keeps_old_version_read_only(client):
    _create(client, kwh=200)
    r = client.post(
        f"/api/accounts/{ACCOUNT}/solar-offsets/{PERIOD}/correct",
        json={"base_version": 1, "offset_kwh": 230, "entered_by": "复核员乙"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["version"] == 2
    assert r.json()["supersedes_id"] is not None

    rows = client.get(f"/api/accounts/{ACCOUNT}/solar-offsets").json()["items"]
    by_version = {row["version"]: row for row in rows}
    assert by_version[2]["is_active"] == 1
    assert by_version[2]["offset_kwh"] == 230
    # The previous version remains as a read-only historical row.
    assert by_version[1]["is_active"] == 0
    assert by_version[1]["offset_kwh"] == 200


def test_correction_requires_matching_explicit_version(client):
    _create(client, kwh=200)
    stale = client.post(
        f"/api/accounts/{ACCOUNT}/solar-offsets/{PERIOD}/correct",
        json={"base_version": 99, "offset_kwh": 230},
    )
    assert stale.status_code == 409
    # Nothing was created by the rejected correction.
    rows = client.get(f"/api/accounts/{ACCOUNT}/solar-offsets").json()["items"]
    assert len(rows) == 1


def test_correct_when_no_active_is_404(client):
    r = client.post(
        f"/api/accounts/{ACCOUNT}/solar-offsets/{PERIOD}/correct",
        json={"base_version": 1, "offset_kwh": 10},
    )
    assert r.status_code == 404


def test_void_deactivates_active_version(client):
    _create(client, kwh=200)
    ok = client.post(
        f"/api/accounts/{ACCOUNT}/solar-offsets/{PERIOD}/void",
        json={"base_version": 1},
    )
    assert ok.status_code == 200
    bad = client.post(
        f"/api/accounts/{ACCOUNT}/solar-offsets/{PERIOD}/void",
        json={"base_version": 1},
    )
    assert bad.status_code == 404


def test_preview_returns_envelope_but_writes_nothing(client):
    _create(client, kwh=200)
    offsets_before = len(
        client.get(f"/api/accounts/{ACCOUNT}/solar-offsets").json()["items"]
    )
    runs_before = len(client.get("/api/history").json()["items"])

    r = client.post(
        "/api/solar-offset/preview",
        json={"account_id": ACCOUNT, "period": PERIOD, "gross_kwh": 400, "peak": False},
    )
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["run_id"] is None
    assert b["has_active_offset"] is True
    assert b["offset_version"] == 1
    assert b["gross_kwh"] == 400
    assert b["offset_kwh"] == 200
    assert b["net_kwh"] == 200
    assert b["total"] == 106.00
    assert all(set(["factor", "price", "amount", "qty"]) <= set(s) for s in b["segments"])

    offsets_after = len(client.get(f"/api/accounts/{ACCOUNT}/solar-offsets").json()["items"])
    runs_after = len(client.get("/api/history").json()["items"])
    assert offsets_after == offsets_before
    assert runs_after == runs_before


def test_preview_floors_net_and_tolerates_missing_offset(client):
    # No offset entered for this period -> treated as zero, still no writes.
    r = client.post(
        "/api/solar-offset/preview",
        json={"account_id": ACCOUNT, "period": "2026-01", "gross_kwh": 50, "peak": False},
    )
    assert r.status_code == 200
    b = r.json()
    assert b["has_active_offset"] is False
    assert b["offset_kwh"] == 0
    assert b["net_kwh"] == 50


def test_bill_with_period_persists_solar_run(client):
    _create(client, kwh=200)
    r = client.post(
        "/api/bill",
        json={"account_id": ACCOUNT, "kwh": 400, "peak": True, "persist": True,
              "period": PERIOD},
    )
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["run_id"] is not None
    assert b["gross_kwh"] == 400 and b["net_kwh"] == 200
    assert b["total"] == 127.20  # net 200 tiered, then x1.2

    run = client.get(f"/api/history/{b['run_id']}").json()
    assert run["kind"] == "solar_bill"


def test_bill_with_period_and_persist_false_writes_no_run(client):
    _create(client, kwh=200)
    runs_before = len(client.get("/api/history").json()["items"])
    r = client.post(
        "/api/bill",
        json={"account_id": ACCOUNT, "kwh": 400, "peak": False, "persist": False,
              "period": PERIOD},
    )
    assert r.status_code == 200
    assert r.json()["run_id"] is None
    assert len(client.get("/api/history").json()["items"]) == runs_before


def test_bill_period_requires_known_account(client):
    r = client.post(
        "/api/bill",
        json={"account_id": 999, "kwh": 100, "period": PERIOD},
    )
    assert r.status_code == 404
