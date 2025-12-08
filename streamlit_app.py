import os
import sys
from pathlib import Path
from typing import List

import streamlit as st
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

# Ensure project root is on sys.path when running via `streamlit run`
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from career_matcher import profile_builder
from career_matcher.rag_retriever import build_reranked_retriever


st.set_page_config(page_title="커리어 매칭 RAG", page_icon="🧭", layout="wide")


@st.cache_resource(show_spinner="LLM 로딩 중...")
def load_llm():
    # TODO: 실제 키를 넣지 말고 환경 변수/Secret Manager를 사용하세요.
    # os.environ.setdefault("OPENAI_API_KEY", "YOUR_API_KEY_HERE")
    return ChatOpenAI(model="gpt-5-mini", temperature=1.0)


@st.cache_resource(show_spinner="벡터 DB + Reranker 준비 중...")
def load_retriever():
    return build_reranked_retriever()


def summarize_profile(parsed_profile: profile_builder.UserProfile) -> str:
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


def build_prompt(mode: str = "recommend"):
    if mode == "resume":
        template = """
당신은 커리어 코치 겸 이력서 컨설턴트입니다.
아래 정보를 토대로 특정 포지션에 맞춘 핵심 문장(이력서 bullet 또는 자기소개서 요약)을 작성하세요.

[사용자 프로필]
{profile}

[대화 기록]
{history}

[관련 컨텍스트]
{context}

지침:
- STAR(상황-과제-행동-성과) 구조를 간단히 반영한 2~3문장을 한 블록으로 제시하세요.
- 정량 지표(%, 배, 시간 단축 등)가 있으면 반영하고, 없으면 합리적 추정치를 제안하십시오.
- 마지막 줄에 "다음 제안" 형태로 추가 사고 방향(예: 강조할 역량, 보완할 데이터)을 1줄 제시하십시오.

[사용자 요청]
{question}
"""
    else:
        template = """
당신은 커리어 매칭 컨설턴트입니다.
아래 정보를 기반으로 사용자의 질문에 답하세요.

[사용자 프로필]
{profile}

[대화 기록]
{history}

[관련 컨텍스트]
{context}

지침:
- 최대 3개의 추천 포지션을 카드 형태로 제시하십시오.
- 각 포지션마다 '이유/강점'을 한 줄로 요약하고, 필요 시 요구 스킬/근무지/경력 조건을 언급하십시오.
- 사용자가 추가 질문을 하도록 다음 행동을 제안하십시오.

[사용자 질문]
{question}
"""
    return ChatPromptTemplate.from_template(template)


def run_rag(question: str, history: List[str], profile_text: str, mode: str = "recommend"):
    retriever = load_retriever()
    docs = retriever.get_relevant_documents(question)
    context = "\n\n".join(doc.page_content for doc in docs)
    prompt = build_prompt(mode=mode)
    chain = prompt | load_llm()
    response = chain.invoke(
        {
            "profile": profile_text,
            "history": "\n".join(history[-5:]),
            "context": context,
            "question": question,
        }
    )
    return response.content, docs


def init_session():
    st.session_state.setdefault("profile", None)
    st.session_state.setdefault("profile_summary", "")
    st.session_state.setdefault("chat_history", [])
    st.session_state.setdefault("conversation", [])
    st.session_state.setdefault("recommended_cards", [])


def main():
    init_session()
    st.title("🧭 커리어 매칭 RAG 챗봇")
    st.caption("dragonkue 임베딩 + BGE Reranker + ChatGPT 기반 맞춤형 공고 추천")

    with st.sidebar:
        st.header("1. 프로필 입력")
        profile_text = st.text_area("직무/스킬/자기소개를 자유롭게 써주세요", height=120)
        if st.button("프로필 분석"):
            if not profile_text.strip():
                st.warning("프로필 내용을 입력하세요.")
            else:
                parsed = profile_builder.build_profile(profile_text)
                summary = summarize_profile(parsed)
                st.session_state.profile = parsed
                st.session_state.profile_summary = summary
                st.success("프로필 분석 완료!")
        if st.session_state.profile_summary:
            st.markdown("### 현재 프로필 요약")
            st.markdown(st.session_state.profile_summary)
            st.markdown("---")
        st.write("**Tip**: `vector_pipeline.py`와 `rag_retriever.py`를 미리 실행해야 검색이 가능합니다.")

    st.subheader("2. 커리어 상담")
    if not st.session_state.profile:
        st.info("왼쪽에서 프로필을 먼저 등록하세요.")
        return

    mode = st.radio(
        "상담 모드 선택",
        options=["추천 받기", "이력서/자소서 문장 생성"],
        horizontal=True,
    )

    extra_input = ""
    project_input = ""
    if mode == "이력서/자소서 문장 생성":
        if st.session_state.recommended_cards:
            card = st.session_state.get("selected_card")
            default_title = card["title"] if card else ""
            st.info("추천 카드 중 하나를 선택하면 해당 포지션명이 자동으로 입력됩니다.")
            extra_input = st.text_input(
                "타깃 포지션 / 회사명",
                value=default_title,
                placeholder="예: 토스증권 ML Engineer",
            )
        else:
            extra_input = st.text_input("타깃 포지션 / 회사명을 적어주세요", placeholder="예: 토스증권 ML Engineer")
        project_input = st.text_area("강조할 프로젝트/성과 (선택 사항)", height=100)

    chat_container = st.container()
    query = st.text_input(
        "질문 또는 요청을 입력하세요",
        placeholder="예: “LLM 경험 살릴 수 있는 포지션 추천해줘”",
    )
    if st.button("추천 받기", use_container_width=True):
        if not query.strip():
            st.warning("질문을 입력해주세요.")
        else:
            mode_key = "resume" if mode == "이력서/자소서 문장 생성" else "recommend"
            user_query = query
            if mode_key == "resume":
                user_query = f"타깃 포지션: {extra_input or '미정'}\n프로젝트/성과: {project_input or '사용자 미입력'}\n요청: {query}"
            with st.spinner("추천을 생성 중..."):
                response, docs = run_rag(
                    user_query,
                    st.session_state.chat_history,
                    st.session_state.profile_summary,
                    mode=mode_key,
                )
                st.session_state.conversation.append(("user", user_query))
                st.session_state.conversation.append(("assistant", response))
                st.session_state.chat_history.append(f"사용자: {user_query}")
                st.session_state.chat_history.append(f"AI: {response}")
                st.session_state["last_docs"] = docs
                if mode_key == "recommend":
                    st.session_state.recommended_cards = [
                        {
                            "title": doc.metadata.get("title", "제목 없음"),
                            "job_id": doc.metadata.get("job_id", ""),
                            "snippet": doc.page_content.splitlines()[0:6],
                        }
                        for doc in docs
                    ]

    with chat_container:
        for role, text in st.session_state.conversation[-10:]:
            with st.chat_message(role):
                st.markdown(text)

    if st.session_state.recommended_cards:
        st.subheader("추천 카드")
        selected_card = st.radio(
            "이력서/자소서 문장을 생성할 포지션을 선택하세요",
            options=range(len(st.session_state.recommended_cards)),
            format_func=lambda idx: st.session_state.recommended_cards[idx]["title"],
            key="selected_card_idx",
        )
        st.session_state["selected_card"] = st.session_state.recommended_cards[selected_card]


if __name__ == "__main__":
    if not os.path.exists("career_matcher/vector_db"):
        st.warning("vector_db가 없습니다. `python career_matcher/vector_pipeline.py --limit 1000`을 먼저 실행하세요.")
    main()
