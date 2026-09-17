import sqlite3
from datetime import datetime, timezone

COLS = (
    "id, account_id, period, version, offset_kwh, source_note, "
    "entered_by, is_active, supersedes_id, created_at"
)


def _row(conn: sqlite3.Connection, sql: str, params: tuple) -> dict | None:
    r = conn.execute(sql, params).fetchone()
    return dict(r) if r else None


def get_active(conn: sqlite3.Connection, account_id: int, period: str) -> dict | None:
    return _row(
        conn,
        f"SELECT {COLS} FROM solar_offsets WHERE account_id=? AND period=? AND is_active=1",
        (account_id, period),
    )


def get(conn: sqlite3.Connection, offset_id: int) -> dict | None:
    return _row(conn, f"SELECT {COLS} FROM solar_offsets WHERE id=?", (offset_id,))


def list_for_account(conn: sqlite3.Connection, account_id: int) -> list[dict]:
    q = (
        f"SELECT {COLS} FROM solar_offsets WHERE account_id=? "
        "ORDER BY period DESC, version DESC, id DESC"
    )
    return [dict(r) for r in conn.execute(q, (account_id,)).fetchall()]


def create(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    period: str,
    offset_kwh: float,
    source_note: str | None,
    entered_by: str | None,
) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    try:
        cur = conn.execute(
            """
            INSERT INTO solar_offsets
                (account_id, period, version, offset_kwh, source_note,
                 entered_by, is_active, supersedes_id, created_at)
            VALUES (?, ?, 1, ?, ?, ?, 1, NULL, ?)
            """,
            (account_id, period, offset_kwh, source_note, entered_by, now),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback()
        raise
    return get(conn, int(cur.lastrowid))


def correct(
    conn: sqlite3.Connection,
    *,
    base: dict,
    offset_kwh: float,
    source_note: str | None,
    entered_by: str | None,
) -> dict:
    """Supersede ``base`` atomically: old row becomes read-only history, new row is active."""
    now = datetime.now(timezone.utc).isoformat()
    try:
        # Deactivate first so the partial unique index never sees two active rows.
        conn.execute("UPDATE solar_offsets SET is_active=0 WHERE id=?", (base["id"],))
        cur = conn.execute(
            """
            INSERT INTO solar_offsets
                (account_id, period, version, offset_kwh, source_note,
                 entered_by, is_active, supersedes_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
            """,
            (
                base["account_id"],
                base["period"],
                base["version"] + 1,
                offset_kwh,
                source_note,
                entered_by,
                base["id"],
                now,
            ),
        )
        new_id = int(cur.lastrowid)
        conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback()
        raise
    return get(conn, new_id)


def deactivate(conn: sqlite3.Connection, offset_id: int) -> bool:
    cur = conn.execute("UPDATE solar_offsets SET is_active=0 WHERE id=? AND is_active=1", (offset_id,))
    conn.commit()
    return cur.rowcount > 0
