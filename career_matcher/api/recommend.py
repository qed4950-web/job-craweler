from datetime import datetime, date
from typing import List

from fastapi import APIRouter, Query

from career_matcher.api.models import JobResultModel, ScoreModel
from career_matcher.app.streamlit_app import load_job_details
from career_matcher.retriever.rag_retriever import (
    RerankedJobRetriever,
    _compute_recency_weight,
    _compute_skill_weight,
    _normalize_distance,
)

router = APIRouter()


@router.get("/recommend", response_model=List[JobResultModel])
def recommend(
    q: str = Query(..., description="검색 쿼리"),
    fetch_k: int = 30,
    top_n: int = 5,
    min_skill: float = 0.0,
    max_age_days: int = 0,
):
    """추천 API 엔드포인트 (n8n/외부 연동 용)."""

    retriever = RerankedJobRetriever(fetch_k=fetch_k, top_n=top_n)

    # 1) 후보군 가져오기
    raw = retriever._search_with_scores(q)  # internal

    results: List[JobResultModel] = []

    for doc, distance in raw:
        meta = doc.metadata or {}
        job_id = meta.get("id") or meta.get("job_id")
        detail = load_job_details(job_id) if job_id else {}
        meta = {**meta, **detail}

        # 2) 점수 계산
        semantic = _normalize_distance(distance)
        recency = _compute_recency_weight(meta.get("posted_at"))
        skill = _compute_skill_weight(q, doc)
        combined = float(round(semantic * 0.7 + recency * 0.2 + skill * 0.1, 5))

        # 3) 필터링
        if skill < min_skill:
            continue

        if max_age_days > 0:
            try:
                d_posted = datetime.strptime(str(meta.get("posted_at"))[:10], "%Y-%m-%d").date()
                if (date.today() - d_posted).days > max_age_days:
                    continue
            except Exception:
                pass

        # 4) 리턴 포맷
        results.append(
            JobResultModel(
                job_id=str(job_id),
                title=meta.get("title"),
                company=meta.get("company"),
                location=meta.get("location"),
                url=meta.get("url"),
                skills=meta.get("skills"),
                posted_at=meta.get("posted_at"),
                due_date=meta.get("due_date"),
                summary=meta.get("summary"),
                scores=ScoreModel(
                    semantic=float(semantic),
                    recency=float(recency),
                    skill=float(skill),
                    combined=combined,
                ),
            )
        )

    results = sorted(results, key=lambda x: x.scores.combined, reverse=True)
    return results[:top_n]
