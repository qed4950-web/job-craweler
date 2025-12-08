import argparse
import json
from pathlib import Path
from typing import Iterable, List, Optional

from career_matcher.configs import settings
from career_matcher.crawler.crawler import crawl_saramin_job_postings
from career_matcher.crawler.storage import JobStorage
from career_matcher.processing.keyword_parser import UserProfile, build_profile


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="프로필 → 키워드 → 크롤러 실행까지 한 번에 수행하는 CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    profile_parser = subparsers.add_parser("profile", help="입력 텍스트에서 검색 키워드 추출")
    profile_parser.add_argument("text", help="직무/스킬/자기소개 자유 텍스트")
    profile_parser.add_argument("--json", action="store_true", help="JSON 포맷으로 출력")

    crawl_parser = subparsers.add_parser("crawl", help="프로필을 기반으로 크롤링 + DB 저장")
    crawl_parser.add_argument("--profile", required=True, help="직무/스킬/자기소개 자유 텍스트")
    crawl_parser.add_argument("--pages", type=int, default=settings.DEFAULT_MAX_PAGES)
    crawl_parser.add_argument("--delay", type=float, default=settings.DEFAULT_LIST_DELAY)
    crawl_parser.add_argument("--export-csv", action="store_true", help="키워드별 CSV 백업")
    return parser.parse_args()


def print_profile(profile: UserProfile, as_json: bool = False) -> None:
    payload = profile.to_search_payload()
    if as_json:
        print(
            json.dumps(
                {"profile": profile.__dict__, "search_payload": payload},
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    print("=== Parsed Profile ===")
    print(f"입력: {profile.raw_text}")
    print(f"직무 후보: {', '.join(profile.job_terms) or '없음'}")
    print(f"스킬 키워드: {', '.join(profile.skill_terms) or '없음'}")
    print(f"희망 지역: {', '.join(profile.location_terms) or '미상'}")
    exp_text = profile.seniority_label or (f"{profile.experience_years}년" if profile.experience_years is not None else "미상")
    print(f"경력: {exp_text}")
    print(f"검색 키워드: {', '.join(profile.suggested_keywords)}")
    print("=== Search Payload ===")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def run_crawl_for_keywords(keywords: Iterable[str], pages: Optional[int], delay: float, export_csv: bool) -> int:
    storage = JobStorage()
    total_inserted = 0
    for keyword in keywords:
        postings = list(crawl_saramin_job_postings(keyword, pages=pages, delay=delay))
        inserted = storage.upsert_postings(postings)
        total_inserted += inserted
        if export_csv:
            storage.export_csv(postings, keyword=keyword)
        print(f"[crawl] keyword='{keyword}' → scraped={len(postings)}, inserted={inserted}")
    return total_inserted


def main():
    args = parse_args()
    if args.command == "profile":
        profile = build_profile(args.text)
        print_profile(profile, as_json=args.json)
        return

    if args.command == "crawl":
        profile = build_profile(args.profile)
        keywords = profile.to_search_payload()["crawler_keywords"]
        inserted = run_crawl_for_keywords(keywords, pages=args.pages, delay=args.delay, export_csv=args.export_csv)
        print(f"[crawl] 완료: 총 {inserted}건 DB 반영")


if __name__ == "__main__":
    main()
