import hashlib
import time
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup

from career_matcher.configs import settings
from career_matcher.crawler.models import JobPosting


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


def crawl_saramin_job_postings(
    search_keyword: str,
    pages: Optional[int] = None,
    delay: float = settings.DEFAULT_LIST_DELAY,
) -> Iterable[JobPosting]:
    """Saramin에서 검색 키워드 기반으로 공고를 크롤링하고 JobPosting 목록을 반환한다."""
    all_job_data: List[JobPosting] = []
    base_url = "https://www.saramin.co.kr/zf_user/search/recruit"

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    max_pages = pages or settings.DEFAULT_MAX_PAGES

    print(f"✅ 검색 키워드: '{search_keyword}'로 최대 {settings.MAX_JOB_COUNT}개의 공고 크롤링 시작...")

    # 페이지 반복
    for page in range(1, max_pages + 1):
        if len(all_job_data) >= settings.MAX_JOB_COUNT:
            break

        params = {
            'search_area': 'main',
            'search_done': 'y',
            'searchType': 'default_mysearch',
            'searchword': search_keyword,
            'recruitPage': page,
            'recruitSort': 'relation',
            'recruitPageCount': settings.JOBS_PER_PAGE
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
            if len(all_job_data) >= settings.MAX_JOB_COUNT:
                break

            job_data = extract_job_data(card)
            job_posting = to_job_posting(job_data)
            all_job_data.append(job_posting)

        print(f"✔️ 페이지 {page} 처리 완료. 현재 공고 수: {len(all_job_data)}개")
        time.sleep(delay)  # 서버 부하를 줄이기 위해 페이지당 지연

    return all_job_data


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


def to_job_posting(job_data: Dict[str, Any]) -> JobPosting:
    """스크랩 결과 dict를 JobPosting dataclass로 변환."""
    url = job_data.get("url", "")
    job_id = extract_job_id(url) if url else hashlib.md5(job_data["title"].encode("utf-8")).hexdigest()
    return JobPosting(
        job_id=job_id,
        title=job_data.get("title", "N/A"),
        company=job_data.get("company", "N/A"),
        location=job_data.get("location", "N/A"),
        salary=job_data.get("salary_etc", "N/A"),
        job_category=job_data.get("job_category", ""),
        career=job_data.get("career", "N/A"),
        education=job_data.get("education", "N/A"),
        due_date=job_data.get("due_date", "N/A"),
        url=url,
        skills="",
        posted_at=None,
        closes_at=job_data.get("due_date"),
        summary="",
        scraped_at=datetime.utcnow(),
    )
