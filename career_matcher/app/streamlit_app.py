import sqlite3
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st

from career_matcher.configs import settings
from career_matcher.processing import keyword_parser
from career_matcher.retriever import rag_retriever
from career_matcher.retriever.rag_retriever import RerankedJobRetriever, _compute_skill_weight, _compute_recency_weight, _normalize_distance
from career_matcher.retriever.reranker import rerank_documents


st.set_page_config(page_title="커리어 매칭 추천", page_icon="🧭", layout="wide")


# ------------------------------------------------------------
# Helpers: DB lookup & metadata enrichment
# ------------------------------------------------------------


def load_job_details(job_id: str) -> Dict[str, Any]:
    """
    SQLite에서 job_id로 상세 정보를 조회해 메타데이터를 보강한다.
    """
    if not job_id:
        return {}
    conn = sqlite3.connect(settings.SQLITE_PATH)
    row = conn.execute(
        """
        SELECT job_id, title, company, location, career, education, job_category,
               skills, summary, url, posted_at, due_date
        FROM job_postings WHERE job_id = ?
        """,
        (job_id,),
    ).fetchone()
    conn.close()
    if not row:
        return {}
    keys = [
        "job_id",
        "title",
        "company",
        "location",
        "career",
        "education",
        "job_category",
        "skills",
        "summary",
        "url",
        "posted_at",
        "due_date",
    ]
    return dict(zip(keys, row))


def enrich_doc_metadata(doc):
    meta = doc.metadata or {}
    job_id = meta.get("id") or meta.get("job_id")
    if job_id:
        extra = load_job_details(job_id)
        merged = {**meta, **extra}
        merged.setdefault("job_id", job_id)
        doc.metadata = merged
    return doc


# ------------------------------------------------------------
# Retriever wrapper with scoring breakdown
# ------------------------------------------------------------


def rank_with_breakdown(
    query: str,
    fetch_k: int,
    top_n: int,
    min_skill: float,
    max_age_days: int,
) -> List[Dict[str, Any]]:
    """
    retriever v2를 활용해 스코어 브레이크다운과 함께 결과 반환.
    """
    retriever = RerankedJobRetriever(fetch_k=fetch_k, top_n=top_n)

    raw = retriever._search_with_scores(query)  # type: ignore[attr-defined]
    if not raw:
        return []

    scored = []
    for doc, distance in raw:
        doc = enrich_doc_metadata(doc)
        semantic = _normalize_distance(distance)
        recency = _compute_recency_weight((doc.metadata or {}).get("posted_at") if isinstance(doc.metadata, dict) else None)
        skill = _compute_skill_weight(query, doc)
        combined = semantic * 0.7 + recency * 0.2 + skill * 0.1

        # recency 필터
        if max_age_days is not None and max_age_days > 0:
            posted = (doc.metadata or {}).get("posted_at")
            try:
                d_posted = datetime.strptime(str(posted)[:10], "%Y-%m-%d").date()
                days_old = (date.today() - d_posted).days
                if days_old > max_age_days:
                    continue
            except Exception:
                pass

        # skill 필터
        if skill < min_skill:
            continue

        scored.append(
            {
                "doc": doc,
                "semantic": semantic,
                "recency": recency,
                "skill": skill,
                "combined": combined,
                "distance": distance,
            }
        )

    # 1차 정렬
    scored.sort(key=lambda x: x["combined"], reverse=True)
    candidate_docs = [s["doc"] for s in scored]

    # reranker 재정렬
    reranked_docs = rerank_documents(candidate_docs, query, top_n=top_n)

    # rerank 결과에 스코어 매핑
    index_by_id = {}
    for s in scored:
        meta = s["doc"].metadata or {}
        key = meta.get("job_id") or meta.get("id") or s["doc"].page_content[:50]
        index_by_id[key] = s

    results = []
    for doc in reranked_docs:
        meta = doc.metadata or {}
        key = meta.get("job_id") or meta.get("id") or doc.page_content[:50]
        base = index_by_id.get(key, {})
        results.append(
            {
                "doc": doc,
                "meta": meta,
                "semantic": base.get("semantic"),
                "recency": base.get("recency"),
                "skill": base.get("skill"),
                "combined": base.get("combined"),
            }
        )
    return results[:top_n]


# ------------------------------------------------------------
# UI helpers
# ------------------------------------------------------------


def render_score_bar(label: str, value: Optional[float], help_text: str = ""):
    col1, col2 = st.columns([1, 3])
    with col1:
        st.caption(label)
    with col2:
        pct = 0.0 if value is None else max(0.0, min(1.0, value)) * 100
        st.progress(pct / 100.0, text=f"{pct:.0f}% {help_text}")


def render_job_card(item: Dict[str, Any]):
    doc = item["doc"]
    meta = item.get("meta", {}) or {}
    title = meta.get("title") or "제목 없음"
    company = meta.get("company") or "회사 정보 없음"
    location = meta.get("location") or "지역 정보 없음"
    url = meta.get("url")
    skills = meta.get("skills", "")
    summary = meta.get("summary") or doc.page_content.splitlines()[1:3]
    combined = item.get("combined")
    recency = item.get("recency")
    skill = item.get("skill")
    semantic = item.get("semantic")

    with st.container(border=True):
        st.markdown(f"### {title}")
        st.markdown(f"**{company}** · {location}")
        cols = st.columns(4)
        cols[0].metric("Combined", f"{(combined or 0)*100:.0f}")
        cols[1].metric("Semantic", f"{(semantic or 0)*100:.0f}")
        cols[2].metric("Recency", f"{(recency or 0)*100:.0f}")
        cols[3].metric("Skill", f"{(skill or 0)*100:.0f}")

        if summary:
            st.write("**요약**")
            if isinstance(summary, list):
                st.markdown("<br>".join(summary), unsafe_allow_html=True)
            else:
                st.write(summary)

        if skills:
            st.write(f"**요구 스킬**: {skills}")
        if url:
            st.link_button("공고 보기", url, use_container_width=True)


def profile_block():
    st.subheader("프로필 입력")
    profile_text = st.text_area("직무/스킬/자기소개를 자유롭게 써주세요", height=140, key="profile_input")
    if st.button("프로필 분석"):
        if not profile_text.strip():
            st.warning("프로필 내용을 입력하세요.")
        else:
            parsed = keyword_parser.build_profile(profile_text)
            summary = summarize_profile(parsed)
            st.session_state.profile = parsed
            st.session_state.profile_summary = summary
            st.session_state.suggested_query = " ".join(parsed.suggested_keywords) or profile_text
            st.success("프로필 분석 완료!")
    if st.session_state.profile_summary:
        st.markdown("### 현재 프로필 요약")
        st.markdown(st.session_state.profile_summary)
        st.info(f"추천 검색어: {st.session_state.get('suggested_query', '')}")


def summarize_profile(parsed_profile: keyword_parser.UserProfile) -> str:
    lines = [
        f"- 직무 후보: {', '.join(parsed_profile.job_terms) or '미정'}",
        f"- 스킬: {', '.join(parsed_profile.skill_terms) or '미정'}",
        f"- 위치: {', '.join(parsed_profile.location_terms) or '무관'}",
    ]
    if parsed_profile.experience_years is not None:
        lines.append(f"- 경력: {parsed_profile.experience_years}년차")
    elif parsed_profile.seniority_label:
        lines.append(f"- 경력 레벨: {parsed_profile.seniority_label}")
    lines.append(f"- 추천 키워드: {', '.join(parsed_profile.suggested_keywords)}")
    return "\n".join(lines)


def ensure_session():
    st.session_state.setdefault("profile", None)
    st.session_state.setdefault("profile_summary", "")
    st.session_state.setdefault("suggested_query", "")
    st.session_state.setdefault("results", [])


# ------------------------------------------------------------
# Main UI
# ------------------------------------------------------------


def tab_recommend():
    st.header("추천 결과")
    col_filters = st.columns(4)
    with col_filters[0]:
        fetch_k = st.number_input("초기 검색 개수 (fetch_k)", min_value=5, max_value=100, value=30, step=5)
    with col_filters[1]:
        top_n = st.number_input("최종 추천 개수 (top_n)", min_value=1, max_value=20, value=5, step=1)
    with col_filters[2]:
        min_skill = st.slider("최소 스킬 매칭", min_value=0, max_value=100, value=30, step=5) / 100.0
    with col_filters[3]:
        max_age_days = st.slider("최근 N일 공고만", min_value=0, max_value=180, value=90, step=15)

    default_query = st.session_state.get("suggested_query", "")
    query = st.text_input("검색 쿼리", value=default_query, placeholder="예: LLM 데이터 엔지니어 포지션 추천")

    if st.button("추천 실행", use_container_width=True):
        if not query.strip():
            st.warning("검색 쿼리를 입력하세요.")
        else:
            with st.spinner("추천 중..."):
                results = rank_with_breakdown(
                    query=query,
                    fetch_k=int(fetch_k),
                    top_n=int(top_n),
                    min_skill=min_skill,
                    max_age_days=int(max_age_days),
                )
                st.session_state.results = results

    if not st.session_state.results:
        st.info("추천 결과가 여기에 표시됩니다.")
        return

    for item in st.session_state.results:
        render_job_card(item)


def tab_skills():
    st.header("스킬 매칭 분석")
    if not st.session_state.results:
        st.info("추천을 먼저 실행하세요.")
        return

    for idx, item in enumerate(st.session_state.results, start=1):
        meta = item.get("meta", {}) or {}
        st.markdown(f"### Top {idx}: {meta.get('title', '제목 없음')}")
        user_skills = set(st.session_state.profile.skill_terms) if st.session_state.profile else set()
        job_skills = set(rag_retriever._extract_skill_tokens(meta.get("skills", "")))  # type: ignore[attr-defined]
        overlap = user_skills.intersection(job_skills)
        st.write(f"사용자 스킬: {', '.join(user_skills) or '없음'}")
        st.write(f"공고 스킬: {', '.join(job_skills) or '없음'}")
        st.success(f"매칭: {', '.join(overlap) or '없음'}")


def tab_profile():
    st.header("프로필 & 설정")
    profile_block()
    st.markdown("---")
    st.caption("벡터 DB 경로: {}".format(settings.VECTOR_DB_DIR))
    st.caption("SQLite 경로: {}".format(settings.SQLITE_PATH))


def main():
    ensure_session()
    if not Path(settings.VECTOR_DB_DIR).exists():
        st.warning("vector_db가 없습니다. `python -m career_matcher.embedding.vector_pipeline --limit 1000`을 먼저 실행하세요.")
    tabs = st.tabs(["추천", "스킬 분석", "프로필/설정"])
    with tabs[0]:
        tab_recommend()
    with tabs[1]:
        tab_skills()
    with tabs[2]:
        tab_profile()


if __name__ == "__main__":
    main()
