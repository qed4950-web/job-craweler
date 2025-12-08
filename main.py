import argparse

from career_matcher.app.cli import print_profile, run_crawl_for_keywords
from career_matcher.embedding.vector_pipeline import build_vector_store, fetch_job_documents
from career_matcher.processing.keyword_parser import build_profile


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Career Matcher main entrypoint.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    profile_parser = subparsers.add_parser("profile", help="프로필에서 키워드 추출")
    profile_parser.add_argument("text", help="직무/스킬/자기소개 자유 텍스트")
    profile_parser.add_argument("--json", action="store_true", help="JSON 포맷 출력")

    crawl_parser = subparsers.add_parser("crawl", help="프로필 기반 크롤링 + DB 반영")
    crawl_parser.add_argument("--profile", required=True, help="직무/스킬/자기소개 자유 텍스트")
    crawl_parser.add_argument("--pages", type=int, default=None, help="페이지 수 제한 (미지정 시 기본값)")
    crawl_parser.add_argument("--delay", type=float, default=None, help="페이지 간 지연 (초)")
    crawl_parser.add_argument("--export-csv", action="store_true", help="키워드별 CSV 백업")

    embed_parser = subparsers.add_parser("embed", help="jobs.db → 벡터 DB 갱신")
    embed_parser.add_argument("--limit", type=int, default=None, help="처리할 문서 수 제한")
    embed_parser.add_argument("--persist-dir", default=None, help="Chroma 저장 경로 (기본: settings.VECTOR_DB_DIR)")
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "profile":
        profile = build_profile(args.text)
        print_profile(profile, as_json=args.json)
        return

    if args.command == "crawl":
        profile = build_profile(args.profile)
        keywords = profile.to_search_payload()["crawler_keywords"]
        pages = args.pages
        from career_matcher.configs import settings

        delay = args.delay if args.delay is not None else settings.DEFAULT_LIST_DELAY
        inserted = run_crawl_for_keywords(keywords, pages=pages, delay=delay, export_csv=args.export_csv)
        print(f"[main] crawl 완료: 총 {inserted}건 DB 반영")
        return

    if args.command == "embed":
        docs = fetch_job_documents(limit=args.limit)
        print(f"[main] fetched {len(docs)} documents for embedding")
        build_vector_store(docs, persist_directory=args.persist_dir)
        print("[main] vector DB 업데이트 완료")


if __name__ == "__main__":
    main()
