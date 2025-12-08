import csv
import hashlib
import os
import sqlite3
import time
from datetime import datetime
from typing import Any, Dict, List
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup

# 최대 가져올 공고 수 설정 (40개씩 페이지를 계산하여 300개에 맞춤)
MAX_JOB_COUNT = 300
JOBS_PER_PAGE = 40
MAX_PAGES = (MAX_JOB_COUNT + JOBS_PER_PAGE - 1) // JOBS_PER_PAGE  # 8 페이지
DB_PATH = os.path.join("career_matcher", "jobs.db")


def extract_job_data(card: BeautifulSoup) -> Dict[str, Any]:
    """하나의 채용 공고 카드에서 데이터를 추출합니다. 기술(skills) 추출 로직 제거됨."""

    # 1. 제목 및 URL
    title_el = card.select_one('h2.job_tit a')
    title = title_el.get_text(strip=True) if title_el else 'N/A'
    relative_url = title_el.get('href', '') if title_el else ''
    url = 'https://www.saramin.co.kr' + relative_url if relative_url else ''

    # 2. 회사명
    company_el = card.select_one('strong.corp_name a') or card.select_one('strong.corp_name')
    company = company_el.get_text(strip=True) if company_el else 'N/A'

    # 3. 주요 조건 추출 (근무지, 경력, 학력, 급여, 마감일 등)
    conditions_el = card.select_one('.job_condition')

    # job_condition 내의 span들을 모두 가져옵니다.
    condition_spans = conditions_el.select('span') if conditions_el else []

    # 텍스트를 추출하고, 불필요한 공백을 제거합니다.
    conditions = [span.get_text(strip=True) for span in condition_spans if span.get_text(strip=True)]

    # 조건들을 구분자에 따라 분리하여 저장 (나중에 데이터 분석을 위해 분리된 채로 유지)
    location = conditions[0] if len(conditions) > 0 else 'N/A'
    career_education = conditions[1] if len(conditions) > 1 else 'N/A'
    salary_etc = conditions[2] if len(conditions) > 2 else 'N/A'

    # 경력/학력 분리 시도 (완벽하지 않을 수 있음)
    career = 'N/A'
    education = 'N/A'
    if '신입' in career_education or '경력' in career_education or '년' in career_education:
        career = career_education
    elif '졸' in career_education or '력무관' in career_education:
        education = career_education

    # 4. 직무 카테고리
    job_category_els = card.select('.job_sector a')
    job_categories = [a.get_text(strip=True) for a in job_category_els]
    job_category = ", ".join(job_categories)

    # 5. 기술/키워드 추출 로직은 사용자 요청에 따라 **제거됨**

    # 6. 마감일 (due_date) 추출 시도
    date_els = card.select('.job_date span')
    due_date = 'N/A'
    if date_els:
        date_text = date_els[0].get_text(strip=True)
        if '~' in date_text:  # 마감일 정보가 "~"로 시작하는 형태일 경우
            due_date = date_text

    return {
        'title': title,
        'company': company,
        'url': url,
        'location': location,
        'career': career,
        'education': education,
        'salary_etc': salary_etc,
        'job_category': job_category,
        'due_date': due_date  # 'skills' 필드가 제거됨
    }


def crawl_saramin_job_postings(search_keyword: str = "데이터 분석") -> List[Dict[str, Any]]:
    """여러 페이지를 순회하며 채용 공고를 크롤링합니다."""
    all_job_data = []
    base_url = "https://www.saramin.co.kr/zf_user/search/recruit"

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    print(f"✅ 검색 키워드: '{search_keyword}'로 최대 {MAX_JOB_COUNT}개의 공고 크롤링 시작...")

    # 페이지 반복
    for page in range(1, MAX_PAGES + 1):
        if len(all_job_data) >= MAX_JOB_COUNT:
            break

        params = {
            'search_area': 'main',
            'search_done': 'y',
            'searchType': 'default_mysearch',
            'searchword': search_keyword,
            'recruitPage': page,
            'recruitSort': 'relation',
            'recruitPageCount': JOBS_PER_PAGE
        }

        try:
            response = requests.get(base_url, params=params, headers=headers)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            print(f"🚨 페이지 요청 중 오류 발생 (페이지 {page}): {e}")
            break

        soup = BeautifulSoup(response.text, 'html.parser')
        job_cards = soup.select('div.item_recruit')

        if not job_cards:
            print(f"ℹ️ 페이지 {page}에서 더 이상 공고를 찾을 수 없습니다. 크롤링을 종료합니다.")
            break

        # 각 공고 카드 데이터 추출
        for card in job_cards:
            if len(all_job_data) >= MAX_JOB_COUNT:
                break

            job_data = extract_job_data(card)
            all_job_data.append(job_data)

        print(f"✔️ 페이지 {page} 처리 완료. 현재 공고 수: {len(all_job_data)}개")
        time.sleep(1)  # 서버 부하를 줄이기 위해 페이지당 1초 지연

    return all_job_data


def save_to_csv(data: List[Dict[str, Any]], filename: str):
    """추출된 데이터를 CSV 파일로 저장합니다."""
    if not data:
        print("저장할 데이터가 없습니다.")
        return

    # CSV 헤더 (컬럼명). 'skills' 필드가 제거됨
    fieldnames = list(data[0].keys())

    try:
        with open(filename, 'w', newline='', encoding='utf-8-sig') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)
        print(f"\n🎉 크롤링 완료! 총 {len(data)}개의 공고를 '{filename}' 파일로 저장했습니다.")
    except Exception as e:
        print(f"🚨 CSV 파일 저장 중 오류 발생: {e}")


def ensure_job_table(conn: sqlite3.Connection) -> None:
    """job_postings 테이블이 없으면 생성하고, 필요한 컬럼을 보장합니다."""
    conn.execute(
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


def extract_job_id(url: str) -> str:
    """URL의 rec_idx(또는 idx) 파라미터를 이용해 job_id를 추출합니다."""
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    for key in ("rec_idx", "idx"):
        if query.get(key):
            return query[key][0]
    path_digits = "".join(filter(str.isdigit, parsed.path))
    if path_digits:
        return path_digits
    seed = f"{url}-{datetime.utcnow().timestamp()}"
    return hashlib.md5(seed.encode("utf-8")).hexdigest()


def upsert_jobs_to_db(data: List[Dict[str, Any]], db_path: str = DB_PATH):
    """크롤링 데이터를 SQLite DB(job_postings)에 upsert합니다."""
    if not data:
        print("DB에 저장할 데이터가 없습니다.")
        return

    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    conn = sqlite3.connect(db_path)
    ensure_job_table(conn)

    scraped_at = datetime.utcnow().isoformat()
    rows = []
    for job in data:
        url = job.get("url", "")
        job_id = extract_job_id(url) if url else hashlib.md5(job["title"].encode("utf-8")).hexdigest()
        rows.append(
            (
                job_id,
                job.get("title", "N/A"),
                job.get("company", "N/A"),
                job.get("location", "N/A"),
                job.get("salary_etc", "N/A"),
                "",
                None,
                job.get("due_date"),
                url,
                scraped_at,
                job.get("career", "N/A"),
                job.get("education", "N/A"),
                job.get("job_category", ""),
                job.get("due_date"),
                "",
            )
        )

    conn.executemany(
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
    conn.close()
    print(f"💾 DB 저장 완료! {len(rows)}개의 공고를 '{db_path}'에 반영했습니다.")


# --- 메인 실행 ---
search_keyword = "데이터 분석"  # 원하시는 키워드로 변경 가능
csv_filename = 'saramin_job_postings_no_skills.csv'  # 파일명을 변경했습니다.
db_path = DB_PATH  # 필요 시 경로를 수정하세요.

# 1. 크롤링 실행
crawled_jobs = crawl_saramin_job_postings(search_keyword)

# 2. CSV 파일 저장
save_to_csv(crawled_jobs, csv_filename)

# 3. SQLite DB 저장
upsert_jobs_to_db(crawled_jobs, db_path)
