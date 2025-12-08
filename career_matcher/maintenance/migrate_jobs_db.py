from __future__ import annotations

import sqlite3
from pathlib import Path

from career_matcher.configs import settings
from career_matcher.crawler.storage import _normalize_date, _normalize_skills


def _log(msg: str) -> None:
    print(f"[migrate_jobs_db] {msg}")


def migrate_jobs_db(db_path: Path | None = None) -> None:
    """
    기존 job_postings 테이블의 skills / posted_at / due_date를
    최신 정규화 규칙(_normalize_*)으로 한 번에 업데이트한다.
    """
    db = db_path or settings.SQLITE_PATH
    db = Path(db)

    if not db.exists():
        raise FileNotFoundError(f"SQLite DB not found: {db}")

    _log(f"Using DB: {db}")

    conn = sqlite3.connect(db)
    cur = conn.cursor()

    cur.execute(
        """
        SELECT job_id, skills, posted_at, due_date
        FROM job_postings
        """
    )
    rows = cur.fetchall()
    _log(f"Loaded {len(rows)} rows from job_postings")

    updates = []
    changed_count = 0

    for job_id, skills, posted_at, due_date in rows:
        norm_skills = _normalize_skills(skills or "")
        norm_posted = _normalize_date(posted_at) if posted_at else None
        norm_due = _normalize_date(due_date) if due_date else None

        if (
            (skills or "") != norm_skills
            or (posted_at or None) != norm_posted
            or (due_date or None) != norm_due
        ):
            updates.append((norm_skills, norm_posted, norm_due, job_id))
            changed_count += 1

    _log(f"Rows to update: {changed_count}")

    if not updates:
        _log("No rows need update. Done.")
        conn.close()
        return

    cur.executemany(
        """
        UPDATE job_postings
        SET skills = ?,
            posted_at = ?,
            due_date = ?
        WHERE job_id = ?
        """,
        updates,
    )
    conn.commit()
    conn.close()

    _log(f"Updated {changed_count} rows. Done.")


if __name__ == "__main__":
    migrate_jobs_db()
