• 준비 끝났어. 지금 상태로 바로 돌리면 돼:

  1. docker compose up -d --build
  2. ./cloudflare_tunnel.sh → 나온 URL을 n8n API 호출에 넣기
  3. n8n 워크플로우 Import → Notion Token/DB ID만 연결

# 커리어 매칭 RAG 파이프라인 - 데이터 수집 모듈

이 폴더는 “직무 키워드 → 채용공고 자동 수집 → DB 저장” 초기 모듈을 담고 있습니다.  
사람인(https://www.saramin.co.kr) 목록 페이지를 대상으로 하며, **서비스 약관·robots.txt를 반드시 확인한 뒤** 연구/검증 목적 내에서만 사용해야 합니다.

## 구성

| 파일 | 설명 |
| --- | --- |
| `career_matcher/crawler/crawler.py` | 키워드 기반 Saramin 리스트 크롤러 (저장은 storage가 담당) |
| `career_matcher/crawler/storage.py` | SQLite 저장/CSV 백업 유틸리티 |
| `career_matcher/processing/keyword_parser.py` | 사용자 입력(직무/스킬/자기소개)에서 검색 키워드를 추출하는 파서/CLI |
| `설명서.md` | 실행 순서와 통합 플로우 |
| `career_matcher/app/cli.py` | 프로필 입력을 받아 keyword_parser → crawler 순으로 실행하는 헬퍼 스크립트 |
| `tests/demo_reranker.py` | BGE reranker + dragonkue 임베딩으로 재순위 검색을 체험하는 데모 |
| `embedding_plan.md` | 임베딩·벡터DB·RAG/Rerank 설계 메모 |
| `career_matcher/embedding/vector_pipeline.py` | jobs.db 데이터를 임베딩해 Chroma 벡터DB로 저장 |
| `career_matcher/retriever/rag_retriever.py` | dragonkue + BGE reranker 기반 retriever 헬퍼 |
| `career_matcher/app/streamlit_app.py` | 프로필 입력 + RAG 상담 Streamlit UI |

## 주요 기능

- `SaraminCrawler`  
  - 요청 헤더/지연/재시도 제어  
  - 페이지별 HTML 요청 후 BeautifulSoup으로 카드 파싱  
  - 직무명, 기업명, 지역, 급여, 요구 스킬, 게시/마감일, 원문 URL을 `JobPosting` dataclass로 정리

- `JobStorage`  
  - SQLite(`career_matcher/data/jobs.db` 기본값)에 job_postings 테이블 생성  
  - `job_id`(rec_idx 파라미터 기준) 단위 upsert

- CSV 백업  
  - `career_matcher/csv/키워드_타임스탬프.csv` 형식, UTF-8

## 사용법

가장 간단한 진입점은 루트의 `main.py` 서브커맨드다.

```bash
# 프로필에서 키워드 추출
python main.py profile "3년차 백엔드인데 LLM 쪽 데이터 분석가"

# 프로필 기반 크롤러 실행 + DB 저장 (+CSV 백업 옵션)
python main.py crawl --profile "3년차 백엔드인데 LLM 쪽 데이터 분석가" --pages 3 --delay 1.0 --export-csv

# 벡터 DB 구축
python main.py embed --limit 500
```

### 입력 파서 (직무/스킬/자기소개 → 키워드)

```bash
python main.py profile "3년차 백엔드인데 LLM 쪽 데이터 분석가로 전환하고 싶어요"

# JSON 출력
python main.py profile "데이터 사이언티스트, 파이썬/SQL 잘함" --json
```

출력에는 직무 후보, 스킬 키워드, 위치, 경력(또는 시니어리티), 추천 검색 키워드, RAG/크롤러에 넘길 payload가 포함됩니다.

### 프로필 → 크롤링 일괄 실행

`main.py crawl --profile ...` 한 줄이면 keyword_parser → crawler → storage까지 순차 실행한다.

### CLI 옵션

| 옵션 | 설명 |
| --- | --- |
| `--profile` | 직무/스킬/자기소개 문장 (crawl 커맨드) |
| `--pages` | 키워드별 최대 페이지 수 |
| `--delay` | 목록 페이지 요청 간 지연(초). 상대 서버 부하를 줄이기 위해 기본 1초 이상 권장 |
| `--export-csv` | 키워드별 CSV 백업 생성 여부 |

### Reranker 데모

요약(summary)이 채워진 공고가 있을 때 다음처럼 재순위 검색을 확인할 수 있습니다.
```bash
pip install --user torch transformers accelerate sentence-transformers
python main.py crawl --profile "데이터 분석가" --pages 1 --delay 1.0 --export-csv
python tests/demo_reranker.py
```
환경에 따라 HuggingFace 모델 로딩에 시간이 걸리거나 GPU/CPU 자원이 필요합니다.

### 벡터 파이프라인 + RAG 연동
1. 벡터 DB 구축  
   ```bash
   python main.py embed --limit 500
   ```
2. Reranker 포함 Retriever 사용  
   ```python
   from career_matcher.retriever.rag_retriever import RerankedJobRetriever

   retriever = RerankedJobRetriever(fetch_k=20, top_n=5)
   docs = retriever.get_relevant_documents("ML Ops 경력 포지션 추천해줘")
   ```
   이 `retriever`를 LangChain RAG 체인 또는 Streamlit 앱에 바로 연결할 수 있습니다.

### Streamlit UI 실행
```bash
streamlit run career_matcher/app/streamlit_app.py --server.address 0.0.0.0 --server.port 8502
```
실행 전 체크리스트:
1. `python main.py crawl --profile "..."`
2. `python main.py embed --limit 1000`
3. OpenAI API 키 환경 변수 설정 (`ChatOpenAI` 사용)

## 수집 필드 (job_postings)

| 필드 | 예시 | 설명 |
| --- | --- | --- |
| `title` | 데이터 분석가 채용 | 공고 제목 |
| `company` | 신한은행 | 회사명 |
| `career` | 신입/경력 | 경력 조건 |
| `education` | 학력무관 / 대졸 | 학력 조건 |
| `location` | 서울 강남구 | 근무지 |
| `salary` | 4,000만원 이상 | 급여/연봉 정보 |
| `job_category` | 데이터·AI, 분석 | 직무 카테고리(목록 뱃지 기준) |
| `skills` | Python, SQL | 키워드/태그 (가능한 경우) |
| `posted_at` | 11.11(월) | 게시일 |
| `due_date` | ~11.28(목) | 마감일 |
| `summary` | 데이터 분석 및 시각화 수행… | 상세 페이지 요약 (`--fetch-summary` 사용 시) |
| `url` | https://www.saramin.co.kr/... | 원문 링크 |
| `scraped_at` | 2025-11-11T05:52:20 | 수집 시각 |

## 개발 메모

- 실제 운영 전 **robots.txt/이용약관/법적 이슈**를 재확인하세요.  
- `requests`/`bs4`가 requirements에 없으면 설치가 필요합니다.  
- 향후 단계:  
  1. 저장된 공고를 전처리해 임베딩 + 벡터 DB 적재  
  2. Streamlit 기반 RAG 챗봇에서 히스토리 포함 질의 응답  
  3. 매칭 점수/스킬 비교 로직 강화

## 라이선스 & 책임

이 스크립트는 학습/프로토타입 목적 예제입니다.  
실제 상용 서비스에 적용하기 전에 해당 사이트 정책과 관련 법령을 반드시 준수하세요.
