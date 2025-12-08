import argparse
import os
import re
import sqlite3
import time
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup
from requests import Response, Session
from urllib.parse import urljoin, urlparse, parse_qs


BASE_URL = "https://www.saramin.co.kr/zf_user/search/recruit"
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
}


@dataclass
class JobPosting:
    job_id: str
    title: str
    company: str
    career: str
    education: str
    location: str
    salary: str
    job_category: str
    skills: str
    posted_at: Optional[str]
    due_date: Optional[str]
    url: str
    summary: str = ""
    scraped_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_db_tuple(self) -> tuple:
        data = asdict(self)
        closes_value = data["due_date"]
        return (
            data["job_id"],
            data["title"],
            data["company"],
            data["location"],
            data["salary"],
            data["skills"],
            data["posted_at"],
            closes_value,
            data["url"],
            data["scraped_at"],
            data["career"],
            data["education"],
            data["job_category"],
            data["due_date"],
            data["summary"],
        )


class JobStorage:
    def __init__(self, db_path: str):
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self._create_table()

    def _create_table(self) -> None:
        self.conn.execute(
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
                scraped_at TEXT
            );
            """
        )
        self.conn.commit()
        self._ensure_columns()

    def _ensure_columns(self) -> None:
        desired_columns = {
            "career": "TEXT",
            "education": "TEXT",
            "job_category": "TEXT",
            "due_date": "TEXT",
            "summary": "TEXT",
        }
        existing = {row[1] for row in self.conn.execute("PRAGMA table_info(job_postings)")}
        altered = False
        for column, definition in desired_columns.items():
            if column not in existing:
                self.conn.execute(f"ALTER TABLE job_postings ADD COLUMN {column} {definition};")
                altered = True
        if altered:
            self.conn.commit()

    def upsert_jobs(self, jobs: Iterable[JobPosting]) -> int:
        query = """
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
        """
        cur = self.conn.cursor()
        batch = [job.to_db_tuple() for job in jobs]
        if not batch:
            return 0
        cur.executemany(query, batch)
        self.conn.commit()
        return cur.rowcount

    def close(self) -> None:
        self.conn.close()


class SaraminCrawler:
    def __init__(
        self,
        session: Optional[Session] = None,
        delay: float = 2.0,
        max_retries: int = 2,
        headers: Optional[Dict[str, str]] = None,
        fetch_summary: bool = False,
        detail_delay: float = 1.0,
    ):
        self.session = session or requests.Session()
        self.delay = delay
        self.max_retries = max_retries
        self.headers = headers or DEFAULT_HEADERS.copy()
        self.fetch_summary = fetch_summary
        self.detail_delay = detail_delay

    def crawl_keyword(self, keyword: str, max_pages: int = 5) -> List[JobPosting]:
        collected: List[JobPosting] = []
        for page in range(1, max_pages + 1):
            html = self._request_page(keyword, page)
            if not html:
                break
            jobs = self._parse_page(html)
            if not jobs:
                break
            self._maybe_enrich_jobs(jobs)
            collected.extend(jobs)
            time.sleep(self.delay)
        return collected

    def _request_page(self, keyword: str, page: int) -> Optional[str]:
        params = {
            "search_type": "search",
            "searchword": keyword,
            "recruitPage": page,
            "recruitSort": "relation",
            "recruitView": "list",
            "paid_fl": "0",
        }
        attempt = 0
        while attempt <= self.max_retries:
            attempt += 1
            try:
                resp: Response = self.session.get(
                    BASE_URL,
                    params=params,
                    headers=self.headers,
                    timeout=15,
                )
            except requests.RequestException as exc:
                print(f"[warn] request error ({keyword}, p{page}): {exc}")
                time.sleep(self.delay * attempt)
                continue

            if resp.status_code == 200:
                return resp.text
            if resp.status_code == 404:
                print(f"[info] no more results for {keyword} (page {page})")
                return None
            if resp.status_code in {429, 503}:
                wait = self.delay * attempt
                print(f"[warn] rate limited ({resp.status_code}); sleeping {wait:.1f}s")
                time.sleep(wait)
                continue

            print(f"[warn] unexpected status {resp.status_code} for page {page}")
            return None
        return None

    def _parse_page(self, html: str) -> List[JobPosting]:
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select("div.item_recruit") or soup.select(".list_item")
        jobs: List[JobPosting] = []
        for card in cards:
            job = self._parse_card(card)
            if job:
                jobs.append(job)
        return jobs

    def _parse_card(self, card) -> Optional[JobPosting]:
        title_el = card.select_one(".job_tit a") or card.select_one("a.job_tit")
        company_el = card.select_one(".corp_name a") or card.select_one(".company_name")
        if not title_el or not company_el:
            return None

        title = title_el.get_text(strip=True)
        company = company_el.get_text(strip=True)
        relative_url = title_el.get("href", "").strip()
        url = urljoin("https://www.saramin.co.kr", relative_url)
        job_id = self._extract_job_id(url) or self._hash_id(title, company, url)

        location = self._extract_text(card, ".job_condition span.work_place") or self._extract_text(
            card, ".job_condition span", join_sep=" "
        )
        salary = self._extract_text(card, ".job_condition span.salary")
        if not salary:
            salary = self._extract_text(card, ".job_condition span", join_sep=" | ")

        career, education = self._extract_career_education(card)

        category_tags = self._get_text_list(card, ".job_sector a")
        job_category = ", ".join(category_tags)

        skill_elements = card.select(".tag span, .toolTip.wrap_keyword span, .toolTip_wrap span, .job_keyword span")
        skill_tags = [element.get_text(strip=True) for element in skill_elements]
        if not skill_tags:
            skill_tags = [badge.get_text(strip=True) for badge in card.select(".job_sector span.badge")]
        if not skill_tags and category_tags:
            skill_tags = category_tags
        skills = ", ".join([tag for tag in skill_tags if tag])

        dates = [span.get_text(strip=True) for span in card.select(".job_date span") or []]
        posted_at, closes_at = self._split_dates(dates)

        return JobPosting(
            job_id=job_id,
            title=title,
            company=company,
            career=career,
            education=education,
            location=location,
            salary=salary,
            job_category=job_category,
            skills=skills,
            posted_at=posted_at,
            due_date=closes_at,
            url=url,
        )

    def _maybe_enrich_jobs(self, jobs: List[JobPosting]) -> None:
        if not self.fetch_summary:
            return
        for job in jobs:
            summary = self._fetch_summary(job.url)
            if summary:
                job.summary = summary

    def _fetch_summary(self, url: str) -> str:
        try:
            resp = self.session.get(url, headers=self.headers, timeout=20)
            if resp.status_code != 200:
                return ""
            soup = BeautifulSoup(resp.text, "html.parser")
            meta_desc = soup.find("meta", attrs={"name": "description"}) or soup.find(
                "meta", attrs={"property": "og:description"}
            )
            if meta_desc and meta_desc.get("content"):
                text = meta_desc["content"].strip()
            else:
                text = ""
            if self.detail_delay:
                time.sleep(self.detail_delay)
            return text[:1000]
        except requests.RequestException:
            return ""

    @staticmethod
    def _extract_text(card, selector: str, join_sep: str = " / ") -> str:
        elements = card.select(selector)
        if not elements:
            return ""
        return join_sep.join(
            element.get_text(strip=True)
            for element in elements
            if element.get_text(strip=True)
        )

    @staticmethod
    def _get_text_list(card, selector: str) -> List[str]:
        elements = card.select(selector)
        values = []
        for element in elements:
            text = element.get_text(strip=True)
            if text:
                values.append(text)
        return values

    @staticmethod
    def _split_dates(dates: List[str]) -> Tuple[Optional[str], Optional[str]]:
        if not dates:
            return None, None
        if len(dates) == 1:
            return dates[0], None
        return dates[0], dates[-1]

    @staticmethod
    def _extract_career_education(card) -> Tuple[str, str]:
        career = ""
        education = ""
        condition_spans = [span.get_text(strip=True) for span in card.select(".job_condition span") if span.get_text(strip=True)]
        for text in condition_spans:
            lowered = text.lower()
            if not career and any(token in lowered for token in ["경력", "신입", "년차"]):
                career = text
            elif not education and any(token in lowered for token in ["학력", "고졸", "대졸", "석사", "박사", "무관"]):
                education = text
        return career, education

    @staticmethod
    def _extract_job_id(url: str) -> Optional[str]:
        query = parse_qs(urlparse(url).query)
        for key in ("rec_idx", "idx"):
            if key in query:
                return query[key][0]
        match = re.search(r"/(\d+)", url)
        return match.group(1) if match else None

    @staticmethod
    def _hash_id(title: str, company: str, url: str) -> str:
        seed = f"{title}-{company}-{url}"
        return str(abs(hash(seed)))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Saramin job crawler with DB persistence.")
    parser.add_argument(
        "--keywords",
        nargs="+",
        required=True,
        help="직무 키워드 목록 (예: 데이터분석가 머신러닝엔지니어)",
    )
    parser.add_argument("--pages", type=int, default=5, help="키워드별 최대 페이지 수")
    parser.add_argument("--delay", type=float, default=2.0, help="요청 사이 지연(초)")
    parser.add_argument(
        "--fetch-summary",
        action="store_true",
        help="상세 페이지를 조회해 summary 필드를 채웁니다 (추가 요청 발생).",
    )
    parser.add_argument(
        "--summary-delay",
        type=float,
        default=1.0,
        help="상세 페이지 요청 사이 지연(초)",
    )
    parser.add_argument(
        "--db-path",
        default="career_matcher/jobs.db",
        help="SQLite 저장 경로",
    )
    parser.add_argument(
        "--csv-dir",
        default="career_matcher/csv",
        help="추가 CSV 백업 디렉터리(선택)",
    )
    return parser.parse_args()


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def dump_csv(jobs: List[JobPosting], csv_dir: str, keyword: str) -> None:
    if not jobs:
        return
    ensure_dir(csv_dir)
    import csv  # lazy import

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = os.path.join(csv_dir, f"{keyword}_{timestamp}.csv")
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "job_id",
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
            ],
        )
        writer.writeheader()
        for job in jobs:
            writer.writerow(asdict(job))
    print(f"[info] CSV saved: {filename}")


def run():
    args = parse_args()
    crawler = SaraminCrawler(
        delay=args.delay,
        fetch_summary=args.fetch_summary,
        detail_delay=args.summary_delay,
    )
    storage = JobStorage(args.db_path)

    try:
        for keyword in args.keywords:
            print(f"[info] crawling keyword: {keyword}")
            jobs = crawler.crawl_keyword(keyword, max_pages=args.pages)
            print(f"[info] fetched {len(jobs)} jobs for keyword '{keyword}'")
            if not jobs:
                continue
            storage.upsert_jobs(jobs)
            dump_csv(jobs, args.csv_dir, keyword)
    finally:
        storage.close()


if __name__ == "__main__":
    run()
