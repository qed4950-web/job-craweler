# 임베딩 & RAG 파이프라인 설계 초안

## 1. 목표
- `job_postings` 테이블과 추가 문서를 임베딩해 벡터 DB에 적재
- Streamlit RAG 챗봇이 “직무 소개 → 내 프로필 묻기 → 매칭 공고 추천” 흐름을 멀티턴으로 수행

## 2. 데이터 소스
1. **채용공고(`job_postings`)**
   - 주요 텍스트: `title`, `company`, `career`, `education`, `location`, `job_category`, `skills`, `summary`, `url`
   - 문장 생성 예:
     ```
     제목: {title}
     회사: {company}
     근무지: {location}
     경력/학력: {career} / {education}
     직무 카테고리: {job_category}
     요구 스킬: {skills}
     요약: {summary}
     링크: {url}
     ```
2. **직무 설명 문서(`job_profiles` 예정)**
   - 직무 키워드, 트렌드 리포트, 스킬 가이드 등 외부 자료

3. **사용자 프로필 입력**
   - `profile_builder` 결과를 세션 state, preference DB 등에 저장하여 추후 검색 파라미터로 재활용

## 3. 임베딩 + 재순위 파이프라인
1. 텍스트 전처리: 공백 정리, 중복 제거, 길이 제한(예: 1k 토큰 이하)
2. 임베딩 모델: `dragonkue/multilingual-e5-small-ko` (이미 vector DB 생성 시 사용)
3. 파이프라인 구성 (의사 코드)
   ```python
   from langchain_community.embeddings import HuggingFaceEmbeddings
   from langchain_community.vectorstores import Chroma

   embeddings = HuggingFaceEmbeddings(model_name="dragonkue/multilingual-e5-small-ko", encode_kwargs={"normalize_embeddings": True})

   documents = [
       Document(page_content=formatted_text, metadata={"job_id": job.job_id, "type": "job_posting"}),
       ...
   ]

   vectordb = Chroma(collection_name="career_jobs", embedding_function=embeddings, persist_directory="career_matcher/vector_db")
   vectordb.add_documents(documents)
   vectordb.persist()
   ```
4. 주기적 업데이트: 크롤러 실행 후 변경된 job_id만 필터링하여 upsert

### 재순위(Reranker)
- 모델: `BAAI/bge-reranker-large` 또는 `bge-reranker-base` (한-영 모두 지원)
- 사용 이유: 1차 벡터 검색(top-k) 후 relevance score를 다시 정렬하여 추천 품질 향상
- LangChain 예시:
  ```python
  from langchain_community.cross_encoders import HuggingFaceCrossEncoder
  from langchain.retrievers import ContextualCompressionRetriever
  from langchain.retrievers.document_compressors import CrossEncoderReranker

  cross_encoder = HuggingFaceCrossEncoder(model_name="BAAI/bge-reranker-large")
  reranker = CrossEncoderReranker(model=cross_encoder, top_n=5)
  compressed_retriever = ContextualCompressionRetriever(
      base_compressor=reranker,
      base_retriever=vectordb.as_retriever(search_kwargs={"k": 20})
  )
  ```
- Streamlit/RAG 체인에서는 `compressed_retriever`를 사용해 상위 5건만 LLM에 전달

## 4. RAG 체인 구조
1. **Retriever**: `Chroma`에서 job_postings + job_profiles를 통합 검색하거나 두 개의 retriever를 구성한 후 결과를 합치는 방식
2. **Prompt**: 
   ```
   역할: 커리어 매칭 컨설턴트
   컨텍스트: {context}
   사용자 프로필: {profile_summary}
   최근 대화: {chat_history}
   사용자 질문: {question}
   ```
3. **LLM**: `ChatOpenAI(model="gpt-5-mini", temperature=0.5~0.7)` 또는 비용 제약 시 로컬 LLM
4. **멀티턴 히스토리**: LangChain `ChatMessageHistory` → session_id별로 저장
5. **추천 단계 분기**
   - Step 1: 직무 설명 문서 기반 요약
   - Step 2: 사용자 프로필 확보(스킬/경력 질문)
   - Step 3: job_postings retriever로 top-k 공고 검색 후 이유/매칭 포인트 설명
   - Step 4: 후속 질문 대응 (공고 상세, 요구 스킬, 트렌드 등)

## 5. 시스템 구성도
```
profile_builder → keyword_runner / crawler → jobs.db
                                  ↓
                          embedding job
                                  ↓
                           vector DB (Chroma)
                                  ↓
Streamlit RAG UI → LLM (ChatOpenAI) ↔ Retriever ↔ vector DB
```

## 6. 개발 순서 제안
1. `job_postings` → Document 포맷 변환 + 임베딩 스크립트 작성
2. Chroma 컬렉션 생성 및 Persist 경로 결정 (`career_matcher/vector_db`)
3. RAG 체인 프로토타입 (`langchain` Runnable) 작성
4. Streamlit UI: 
   - 좌측: 사용자 프로필 입력 + 키워드 추천
   - 우측: 챗봇 대화 + 추천 공고 카드
5. 테스트 시나리오 마련: 
   - “데이터 사이언티스트” → 트렌드 요약 → “3년차 Python, SQL 가능” → 추천 공고 3건
6. 성능/품질 피드백: 검색 k값, rerank 필요 여부, summary 품질 검토

## 7. 향후 확장
- reranker 모델(BGE, Cohere rerank)로 추천 정확도 향상
- 사용자 프로필 DB화 → 반복 접속 시 개인화된 추천
- 알림 시스템: 신규 공고가 프로필과 매칭되면 이메일/슬랙 알림
- 다언어 지원: 영어/일본어 등 해외 공고 확장 시 멀티 언어 임베딩 모델 교체
