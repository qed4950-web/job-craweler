import csv
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

from career_matcher.configs import settings
from career_matcher.crawler.models import JobPosting


class JobStorage:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path) if db_path else settings.SQLITE_PATH
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS job_postings (
                    job_id TEXT PRIMARY KEY,
                    title TEXT,
                    company TEXT,
                    location TEXT,
                    salary TEXT,
                    skills TEXT,
                    posted_at TEXT,
                    closes_at TEXT,
                    url TEXT,
                    scraped_at TEXT,
                    career TEXT,
                    education TEXT,
                    job_category TEXT,
                    due_date TEXT,
                    summary TEXT
                );
                """
            )
            conn.commit()

    def upsert_postings(self, postings: Iterable[JobPosting]) -> int:
        rows = [
            (
                p.job_id,
                p.title,
                p.company,
                p.location,
                p.salary,
                p.skills,
                p.posted_at,
                p.closes_at,
                p.url,
                p.scraped_at.isoformat(),
                p.career,
                p.education,
                p.job_category,
                p.due_date,
                p.summary or "",
            )
            for p in postings
        ]
        if not rows:
            return 0

        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.executemany(
                """
                INSERT INTO job_postings (
                    job_id, title, company, location, salary, skills,
                    posted_at, closes_at, url, scraped_at,
                    career, education, job_category, due_date, summary
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    title=excluded.title,
                    company=excluded.company,
                    location=excluded.location,
                    salary=excluded.salary,
                    skills=excluded.skills,
                    posted_at=excluded.posted_at,
                    closes_at=excluded.closes_at,
                    url=excluded.url,
                    scraped_at=excluded.scraped_at,
                    career=excluded.career,
                    education=excluded.education,
                    job_category=excluded.job_category,
                    due_date=excluded.due_date,
                    summary=excluded.summary;
                """,
                rows,
            )
            conn.commit()
            return cur.rowcount

    def export_csv(self, postings: Iterable[JobPosting], keyword: str) -> Path:
        settings.CSV_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = settings.CSV_DIR / f"{keyword}_{ts}.csv"

        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "title",
                    "company",
                    "career",
                    "education",
                    "location",
                    "salary",
                    "job_category",
                    "skills",
                    "posted_at",
                    "due_date",
                    "summary",
                    "url",
                    "scraped_at",
                ]
            )
            for p in postings:
                writer.writerow(
                    [
                        p.title,
                        p.company,
                        p.career,
                        p.education,
                        p.location,
                        p.salary,
                        p.job_category,
                        p.skills,
                        p.posted_at or "",
                        p.due_date,
                        p.summary or "",
                        p.url,
                        p.scraped_at.isoformat(),
                    ]
                )
        return path
