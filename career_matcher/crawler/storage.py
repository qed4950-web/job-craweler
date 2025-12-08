from __future__ import annotations

import csv
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, Optional

from career_matcher.configs import settings
from career_matcher.crawler.models import JobPosting


# -----------------------------
# Skill 정규화 유틸
# -----------------------------

# 1차 synonym map (필요 시 확장)
_SKILL_SYNONYMS: dict[str, str] = {
    "python3": "python",
    "python2": "python",
    "py": "python",
    "js": "javascript",
    "ts": "typescript",
    "nodejs": "node",
    "postgresql": "postgres",
    "postgre": "postgres",
    "tf": "tensorflow",
    "sklearn": "scikit-learn",
    "scikitlearn": "scikit-learn",
    "pytorch": "torch",
    "tf2": "tensorflow",
    "tf1": "tensorflow",
    "ml": "ml",
    "machinelearning": "ml",
    "machine-learning": "ml",
    "gpt": "gpt",
}


def _clean_skill_token(raw: str) -> str:
    """개별 스킬 토큰을 소문자 + 기호 정리 + synonym 적용."""
    if not raw:
        return ""
    token = raw.strip().lower()
    # 공백/구두점 등 제거 (C#, C++ 같은 건 최대한 유지)
    token = re.sub(r"[^\w#+.+-]", "", token)
    if not token:
        return ""
    return _SKILL_SYNONYMS.get(token, token)


def _normalize_skills(skills: str | None) -> str:
    """
    skills 문자열을 소문자/여러 구분자 기준으로 정규화.
    - '/', '|', ',', ';' 등으로 분리
    - 공백/특수문자 정리
    - synonym 매핑
    - 순서를 유지한 중복 제거
    """
    if not skills:
        return ""

    tmp = (
        skills.replace("/", " ")
        .replace("|", " ")
        .replace(",", " ")
        .replace(";", " ")
    )
    raw_tokens = tmp.split()
    seen: set[str] = set()
    normalized: list[str] = []

    for raw in raw_tokens:
        t = _clean_skill_token(raw)
        if not t:
            continue
        if t in seen:
            continue
        seen.add(t)
        normalized.append(t)

    return ", ".join(normalized)


# -----------------------------
# Date 정규화 유틸
# -----------------------------


def _try_parse_with_formats(value: str, patterns: list[str]) -> Optional[datetime]:
    for fmt in patterns:
        try:
            return datetime.strptime(value, fmt)
        except Exception:
            continue
    return None


def _normalize_date(value: str | None) -> str | None:
    """
    날짜 문자열을 최대한 YYYY-MM-DD로 정규화.
    실패하면 원본을 그대로 반환해서 정보 손실은 막는다.

    처리 패턴 예:
    - '2025-01-02', '2025/01/02', '2025.01.02'
    - '11.11(월)', '11.11'
    - '3일 전', '오늘', '어제'
    """
    if not value:
        return None

    s = str(value).strip()
    if not s:
        return None

    # 1) 이미 YYYY-MM-DD 형태인 경우
    try:
        dt = datetime.strptime(s[:10], "%Y-%m-%d")
        return dt.strftime("%Y-%m-%d")
    except Exception:
        pass

    # 2) 상대 날짜: "3일 전"
    m = re.match(r"(\d+)일\s*전", s)
    if m:
        days_ago = int(m.group(1))
        dt = datetime.now() - timedelta(days=days_ago)
        return dt.strftime("%Y-%m-%d")

    # 3) "오늘", "어제"
    if s.startswith("오늘"):
        return datetime.now().strftime("%Y-%m-%d")
    if s.startswith("어제"):
        return (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    # 4) "11.11(월)" / "11.11" / "~11.11(월)" 같은 형식
    cleaned = s.split("(")[0].replace("~", "").strip()
    if re.match(r"^\d{1,2}\.\d{1,2}$", cleaned):
        try:
            month_str, day_str = cleaned.split(".")
            year = datetime.now().year
            dt = datetime(year, int(month_str), int(day_str))
            return dt.strftime("%Y-%m-%d")
        except Exception:
            pass

    # 5) 몇 가지 일반 포맷 시도
    patterns = [
        "%Y.%m.%d",
        "%Y/%m/%d",
        "%Y-%m-%d",
        "%y.%m.%d",
        "%y/%m/%d",
        "%y-%m-%d",
    ]
    dt2 = _try_parse_with_formats(cleaned, patterns)
    if dt2:
        return dt2.strftime("%Y-%m-%d")

    # 6) 끝까지 안되면 원본 그대로 보존
    return s


# -----------------------------
# JobStorage 본체
# -----------------------------


class JobStorage:
    """
    크롤링 결과 JobPosting을 SQLite에 저장/업데이트하는 저장소.
    - job_id PRIMARY KEY, upsert 기반
    - 입력 시 skill/date 정규화 수행
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path) if db_path else settings.SQLITE_PATH
        self._ensure_tables()
        self._ensure_indexes()

    # ---------- Schema / Index ----------

    def _ensure_tables(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS job_postings (
                    job_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
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

    def _ensure_indexes(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_job_postings_scraped_at "
                "ON job_postings(scraped_at DESC);"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_job_postings_posted_at "
                "ON job_postings(posted_at);"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_job_postings_skills "
                "ON job_postings(skills);"
            )
            conn.commit()

    # ---------- Upsert / Export ----------

    def upsert_postings(self, postings: Iterable[JobPosting]) -> int:
        """
        JobPosting 리스트를 upsert.
        skills, posted_at, closes_at, due_date는 이 단계에서 모두 정규화된다.
        """
        rows = []
        for p in postings:
            norm_skills = _normalize_skills(p.skills)
            norm_posted = _normalize_date(p.posted_at) if p.posted_at else None
            norm_closes = _normalize_date(p.closes_at) if p.closes_at else None
            norm_due = _normalize_date(p.due_date) if p.due_date else None

            rows.append(
                (
                    p.job_id,
                    p.title,
                    p.company,
                    p.location,
                    p.salary,
                    norm_skills,
                    norm_posted,
                    norm_closes,
                    p.url,
                    p.scraped_at.isoformat(),
                    p.career,
                    p.education,
                    p.job_category,
                    norm_due,
                    p.summary or "",
                )
            )

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
        """
        크롤링 직후 raw JobPosting 리스트를 CSV로 저장.
        여기서도 skills/posted_at/due_date 정규화해서 기록.
        """
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
                        _normalize_skills(p.skills),
                        _normalize_date(p.posted_at) or "",
                        _normalize_date(p.due_date) or "",
                        p.summary or "",
                        p.url,
                        p.scraped_at.isoformat(),
                    ]
                )
        return path
