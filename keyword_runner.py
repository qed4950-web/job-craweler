"""
profile_builder에서 파생된 키워드 세트를 받아 crawler.py를 순차 실행하는 도우미입니다.

사용법:
    python career_matcher/keyword_runner.py \
        --profile "3년차 백엔드인데 LLM 쪽 데이터 분석가" \
        --pages 5 \
        --delay 3 \
        --fetch-summary

또는 JSON 파일로 여러 프로필을 넘겨 반복 실행할 수도 있습니다.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import List, Sequence


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CRAWLER_SCRIPT = PROJECT_ROOT / "career_matcher" / "crawler.py"
PROFILE_SCRIPT = PROJECT_ROOT / "career_matcher" / "profile_builder.py"


def run_profile_builder(text: str) -> List[str]:
    """profile_builder.py를 호출해 crawler_keywords를 반환."""
    cmd = [
        sys.executable,
        str(PROFILE_SCRIPT),
        text,
        "--json",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    payload = json.loads(result.stdout)
    return payload["search_payload"]["crawler_keywords"]


def run_crawler(keywords: Sequence[str], args: argparse.Namespace) -> None:
    """crawler.py를 CLI 인자와 함께 실행."""
    cmd = [
        sys.executable,
        str(CRAWLER_SCRIPT),
        "--keywords",
        *keywords,
        "--pages",
        str(args.pages),
        "--delay",
        str(args.delay),
        "--db-path",
        args.db_path,
        "--csv-dir",
        args.csv_dir,
    ]
    if args.fetch_summary:
        cmd.append("--fetch-summary")
        cmd.extend(["--summary-delay", str(args.summary_delay)])

    print(f"[runner] executing crawler with keywords={keywords}")
    subprocess.run(cmd, check=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="profile 기반 키워드로 crawler를 실행합니다.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--profile", help="단일 사용자 입력 문장")
    group.add_argument("--profile-file", help="JSON/텍스트 파일 (각 줄이 한 문장)")

    parser.add_argument("--pages", type=int, default=5)
    parser.add_argument("--delay", type=float, default=2.0)
    parser.add_argument("--fetch-summary", action="store_true")
    parser.add_argument("--summary-delay", type=float, default=0.5)
    parser.add_argument("--db-path", default=str(PROJECT_ROOT / "career_matcher" / "jobs.db"))
    parser.add_argument("--csv-dir", default=str(PROJECT_ROOT / "career_matcher" / "csv"))
    return parser.parse_args()


def load_profiles_from_file(path: str) -> List[str]:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"profile file not found: {path}")
    if file_path.suffix.lower() == ".json":
        data = json.loads(file_path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [str(item) for item in data]
        raise ValueError("JSON 파일은 문자열 리스트여야 합니다.")
    # 일반 텍스트 파일 (줄 구분)
    return [line.strip() for line in file_path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main():
    args = parse_args()
    profiles: List[str]
    if args.profile:
        profiles = [args.profile]
    else:
        profiles = load_profiles_from_file(args.profile_file)

    for profile_text in profiles:
        print(f"[runner] profile input: {profile_text}")
        keywords = run_profile_builder(profile_text)
        if not keywords:
            print("[runner] no keywords extracted; skipping.")
            continue
        run_crawler(keywords, args)


if __name__ == "__main__":
    main()
