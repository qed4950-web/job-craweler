import argparse
import json
import re
from dataclasses import dataclass, asdict, field
from typing import Dict, List, Optional, Tuple


JOB_CATALOG: Dict[str, List[str]] = {
    "데이터 분석가": ["데이터 분석가", "data analyst", "데이터 분석"],
    "데이터 사이언티스트": ["데이터 사이언티스트", "data scientist"],
    "머신러닝 엔지니어": ["머신러닝 엔지니어", "ml engineer", "머신러닝 엔지너"],
    "AI 제품 매니저": ["ai pm", "ai product manager", "ai 제품 매니저"],
    "백엔드 개발자": ["백엔드", "backend", "server developer"],
    "프론트엔드 개발자": ["프론트엔드", "frontend", "front-end"],
    "데이터 엔지니어": ["데이터 엔지니어", "data engineer"],
    "MLOps 엔지니어": ["mlops", "ml ops", "ml ops engineer"],
}

SKILL_CATALOG: Dict[str, List[str]] = {
    "Python": ["python", "파이썬"],
    "SQL": ["sql"],
    "R": [" r ", " r언어", "r programming"],
    "TensorFlow": ["tensorflow", "텐서플로"],
    "PyTorch": ["pytorch", "파이토치"],
    "LLM": ["llm", "large language model", "대형 언어 모델"],
    "데이터 시각화": ["tableau", "power bi", "시각화"],
    "클라우드": ["aws", "gcp", "azure"],
    "MLOps": ["mlops", "ml ops"],
    "API 설계": ["api", "rest", "grpc"],
}

LOCATION_CATALOG: Dict[str, List[str]] = {
    "서울": ["서울", "seoul"],
    "경기": ["경기", "gyeonggi"],
    "부산": ["부산", "busan"],
    "대구": ["대구", "daegu"],
    "인천": ["인천", "incheon"],
    "대전": ["대전", "daejeon"],
    "광주": ["광주", "gwangju"],
}

SENIORITY_KEYWORDS: Dict[str, Tuple[int, str]] = {
    "신입": (0, "Entry"),
    "주니어": (2, "Junior"),
    "미드": (4, "Mid"),
    "시니어": (6, "Senior"),
    "리드": (8, "Lead"),
}

EXPERIENCE_PATTERN = re.compile(r"(\d+)\s*년(?:차)?")


@dataclass
class UserProfile:
    raw_text: str
    job_terms: List[str] = field(default_factory=list)
    skill_terms: List[str] = field(default_factory=list)
    location_terms: List[str] = field(default_factory=list)
    experience_years: Optional[int] = None
    seniority_label: Optional[str] = None
    suggested_keywords: List[str] = field(default_factory=list)
    notes: str = ""

    def to_search_payload(self) -> Dict[str, List[str]]:
        crawler_keywords = self.suggested_keywords or [self.raw_text.strip()]
        rag_query_terms = self.job_terms + self.skill_terms
        if not rag_query_terms:
            rag_query_terms = crawler_keywords
        return {
            "crawler_keywords": crawler_keywords,
            "rag_query_terms": rag_query_terms,
        }


def normalize(text: str) -> str:
    return " ".join(text.strip().lower().split())


def match_catalog(text: str, catalog: Dict[str, List[str]]) -> List[str]:
    hits: List[str] = []
    for canonical, variants in catalog.items():
        tokens = set([canonical.lower(), *[v.lower() for v in variants]])
        if any(token.strip() and token.strip() in text for token in tokens):
            hits.append(canonical)
    # remove duplicates while preserving order
    seen = set()
    ordered = []
    for item in hits:
        if item not in seen:
            ordered.append(item)
            seen.add(item)
    return ordered


def extract_experience(text: str) -> Tuple[Optional[int], Optional[str]]:
    match = EXPERIENCE_PATTERN.search(text)
    if match:
        years = int(match.group(1))
        return years, None
    for keyword, (years, label) in SENIORITY_KEYWORDS.items():
        if keyword in text:
            return years, label
    return None, None


def expand_keywords(job_terms: List[str], skill_terms: List[str], raw_text: str) -> List[str]:
    keywords = job_terms + skill_terms
    if not keywords:
        tokens = [token for token in re.split(r"[,\s/]+", raw_text) if len(token) > 1]
        keywords = tokens[:3] or [raw_text.strip()]
    return list(dict.fromkeys(keywords))


def build_profile(text: str) -> UserProfile:
    normalized = normalize(text)
    job_terms = match_catalog(normalized, JOB_CATALOG)
    skill_terms = match_catalog(normalized, SKILL_CATALOG)
    location_terms = match_catalog(normalized, LOCATION_CATALOG)
    experience_years, seniority_label = extract_experience(normalized)

    profile = UserProfile(
        raw_text=text,
        job_terms=job_terms,
        skill_terms=skill_terms,
        location_terms=location_terms,
        experience_years=experience_years,
        seniority_label=seniority_label,
        notes="입력 텍스트 기반 자동 추출 결과입니다. 필요 시 관리자 승인 후 수정하세요.",
    )
    profile.suggested_keywords = expand_keywords(job_terms, skill_terms, text)
    return profile


def run_cli():
    parser = argparse.ArgumentParser(description="사용자 입력에서 직무/스킬 키워드를 추출합니다.")
    parser.add_argument("text", help="직무 혹은 스킬/자기소개 문장")
    parser.add_argument(
        "--json",
        action="store_true",
        help="JSON 포맷으로 결과 출력",
    )
    args = parser.parse_args()

    profile = build_profile(args.text)
    payload = profile.to_search_payload()

    if args.json:
        print(json.dumps({"profile": asdict(profile), "search_payload": payload}, ensure_ascii=False, indent=2))
    else:
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


if __name__ == "__main__":
    run_cli()
