"""
벡터 DB + BGE reranker 기반 Job Retriever v2

역할:
- Chroma 벡터DB에서 fetch_k개 문서 가져오기
- 쿼리와의 의미 유사도(semantic score) 계산
- 게시일(posted_at) 기반 recency 가중치
- skills 메타데이터 기반 skill-match 가중치
- BGE reranker(rerank_documents)를 사용해 최종 순위 재정렬
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document

from career_matcher.configs import settings
from career_matcher.embedding.embedding_models import get_embedding_model
from career_matcher.retriever.reranker import rerank_documents


# ----------------------------
# Dataclass for internal scoring
# ----------------------------


@dataclass
class ScoredDoc:
    doc: Document
    distance: float
    semantic_score: float
    recency_weight: float
    skill_weight: float

    @property
    def combined_score(self) -> float:
        """
        semantic + recency + skill을 합친 기본 점수.
        가중치는 필요하면 settings 또는 상수로 조정 가능.
        """
        # 기본 값: semantic 0.7, recency 0.2, skill 0.1
        return (
            self.semantic_score * 0.7
            + self.recency_weight * 0.2
            + self.skill_weight * 0.1
        )


# ----------------------------
# Utility functions
# ----------------------------


def _normalize_distance(distance: float) -> float:
    """
    Chroma similarity_search_with_score 의 distance를 0~1 semantic score로 변환.
    일반적으로 distance는 작을수록 유사도가 높음.
    """
    return 1.0 / (1.0 + distance)


def _parse_date_yyyy_mm_dd(value: Any) -> Optional[date]:
    if not value:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        s = str(value)
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def _compute_recency_weight(posted_at: Optional[Any]) -> float:
    """
    posted_at (YYYY-MM-DD) 기준으로 최근일수록 점수 높게.
    예: 오늘이면 거의 1, 60일 전이면 0.5 근처, 180일 전이면 더 작게.
    """
    base = 0.3  # 정보 없을 때 최소 가중치
    d = _parse_date_yyyy_mm_dd(posted_at)
    if not d:
        return base

    today = date.today()
    days = max((today - d).days, 0)
    # 지수 감쇠: 0일 → 1.0, 30일 → ~0.7, 90일 → ~0.37
    weight = math.exp(-days / 60.0)
    return max(base, min(1.0, weight))


def _extract_skill_tokens(skills_str: Optional[str]) -> List[str]:
    if not skills_str:
        return []
    raw = (
        skills_str.replace("/", " ")
        .replace(",", " ")
        .replace("|", " ")
        .lower()
    )
    tokens = [t.strip() for t in raw.split() if t.strip()]
    return sorted(set(tokens))


def _compute_skill_weight(query: str, doc: Document) -> float:
    """
    query 안에 있는 단어와 doc.metadata["skills"]의 겹치는 정도를 기반으로 가중치 계산.
    - skills가 없으면 0.3 정도의 기본값
    - 어느 정도 매칭되면 0.6~0.9 사이
    """
    skills_str = doc.metadata.get("skills") if isinstance(doc.metadata, dict) else None
    skill_tokens = _extract_skill_tokens(skills_str)
    if not skill_tokens:
        return 0.3

    q_raw = (
        query.replace("/", " ")
        .replace(",", " ")
        .replace("|", " ")
        .lower()
    )
    q_tokens = {t.strip() for t in q_raw.split() if t.strip()}
    if not q_tokens:
        return 0.3

    overlap = q_tokens.intersection(skill_tokens)
    if not overlap:
        return 0.3

    ratio = len(overlap) / len(skill_tokens)
    return max(0.3, min(1.0, 0.3 + ratio * 0.7))


# ----------------------------
# Main Retriever
# ----------------------------


class RerankedJobRetriever:
    """
    dragonkue 임베딩 + Chroma + BGE reranker 기반 Job Retriever.

    사용 예:
        from career_matcher.retriever.rag_retriever import RerankedJobRetriever

        retriever = RerankedJobRetriever(fetch_k=30, top_n=10)
        docs = retriever.get_relevant_documents("LLM 경험 있는 데이터 엔지니어")
    """

    def __init__(
        self,
        fetch_k: int = 20,
        top_n: int = 5,
        persist_directory: Optional[str] = None,
        collection_name: Optional[str] = None,
    ) -> None:
        self.fetch_k = fetch_k
        self.top_n = top_n

        persist_directory = persist_directory or str(settings.VECTOR_DB_DIR)
        collection_name = (
            collection_name
            or getattr(settings, "CHROMA_COLLECTION_NAME", "job_postings")
        )

        embeddings = get_embedding_model()
        self.vectordb = Chroma(
            persist_directory=persist_directory,
            embedding_function=embeddings,
            collection_name=collection_name,
        )

    def get_relevant_documents(self, query: str) -> List[Document]:
        """
        메인 엔트리: 쿼리에 대해 top_n개 추천 문서 반환.
        """
        raw_candidates = self._search_with_scores(query)
        if not raw_candidates:
            return []

        scored_candidates = [self._score_candidate(query, doc, distance) for doc, distance in raw_candidates]
        scored_candidates.sort(key=lambda x: x.combined_score, reverse=True)

        candidate_docs = [sd.doc for sd in scored_candidates]

        reranked_docs = rerank_documents(candidate_docs, query, top_n=self.top_n)
        return reranked_docs

    def _search_with_scores(self, query: str) -> List[Tuple[Document, float]]:
        """Chroma similarity_search_with_score 래핑."""
        try:
            results = self.vectordb.similarity_search_with_score(
                query,
                k=self.fetch_k,
            )
        except Exception as e:
            print(f"[RerankedJobRetriever] search error: {e}")
            return []
        return results

    def _score_candidate(self, query: str, doc: Document, distance: float) -> ScoredDoc:
        semantic_score = _normalize_distance(distance)
        recency_weight = _compute_recency_weight(
            (doc.metadata or {}).get("posted_at") if isinstance(doc.metadata, dict) else None
        )
        skill_weight = _compute_skill_weight(query, doc)

        return ScoredDoc(
            doc=doc,
            distance=distance,
            semantic_score=semantic_score,
            recency_weight=recency_weight,
            skill_weight=skill_weight,
        )


# ----------------------------
# Simple CLI demo
# ----------------------------


def demo(query: str, persist_directory: Optional[str] = None) -> None:
    """
    간단한 데모:
        python -m career_matcher.retriever.rag_retriever "데이터 엔지니어"
    """
    retriever = RerankedJobRetriever(
        fetch_k=30,
        top_n=5,
        persist_directory=persist_directory,
    )
    docs = retriever.get_relevant_documents(query)

    if not docs:
        print("[demo] 결과가 없습니다.")
        return

    for idx, doc in enumerate(docs, start=1):
        meta = doc.metadata or {}
        title = meta.get("title", "제목 없음")
        company = meta.get("company", "회사 정보 없음")
        location = meta.get("location", "지역 정보 없음")
        skills = meta.get("skills", "")

        print(f"Top {idx}: {title} / {company}")
        print(f" - location: {location}")
        if skills:
            print(f" - skills: {skills}")
        print(" - preview:")
        for line in doc.page_content.splitlines()[:3]:
            print(f"   {line}")
        print("-" * 50)


if __name__ == "__main__":
    sample_query = "LLM 경험 있는 데이터 엔지니어 포지션 추천해줘"
    demo(sample_query)
