# Career Matcher RAG Pipeline  
**Profile → Keywords → Job Crawling → SQLite → Embedding → Vector DB → RAG Matching System**

이 프로젝트는 사용자의 **프로필/경력/스킬 → 추천 검색 키워드 생성 → 사람인 채용공고 자동 수집 → 임베딩 기반 RAG 검색 → 추천 결과 제공**까지  
엔드투엔드로 자동화하는 커리어 매칭 파이프라인입니다.

Docker 기반으로 배포할 수 있으며, Cloudflare Tunnel + n8n과 연동하면  
**무료로 자동화된 커리어 추천 API 시스템**으로 사용할 수 있습니다.

---

# 🚀 Features

### 🔍 Keyword Parser  
- 자연어 프로필 입력 → 직무/스킬/시니어리티 → 추천 검색 키워드 생성  
- 예:  
  ```
  "3년차 백엔드인데 LLM 쪽 데이터 분석가로 전환하고 싶음"
  ```

### 🕸 Saramin Job Crawler  
- 검색 키워드 기반 채용공고 수집  
- 기업명, 직무, 위치, 급여, 스킬 태그, 게시일/마감일, 상세 URL 등 저장  
- CSV 백업 자동 생성

### 💾 SQLite Job Storage  
- job_postings 테이블 자동 생성  
- rec_idx 기준 upsert  
- pipeline-friendly 구조

### 🔮 Embedding & Vector DB  
- Chroma 벡터 DB 저장  
- dragonkue 임베딩 + BGE reranker 기반 RAG  
- "나에게 맞는 포지션 추천" 질의 가능

### 🧠 RAG Retriever  
- fetch_k / top_n 조절 가능  
- 스킬 매칭 점수 기반 재순위

### 🖥 Streamlit UI  
- 프로필 입력 → RAG 상담  
- 로컬/원격 배포 모두 가능

### 🐳 Docker Deployment  
- 단일 명령으로 전체 환경 실행  
- Cloudflare Tunnel로 외부 접근 URL 자동 제공

---

# 📌 Architecture Overview  
```
Profile → KeywordParser → JobCrawler → SQLite → VectorPipeline → Chroma DB  
         ↓                                                           ↓
      JSON Payload                                          RAG Retriever (embedding+rerank)
```

---

# ⚡ Quickstart

## 1) Clone
```bash
git clone https://github.com/qed4950-web/job-craweler
cd job-craweler
```

## 2) Docker 실행  
```bash
docker compose up -d --build
```

## 3) Cloudflare Tunnel 실행  
```bash
./cloudflare_tunnel.sh
```

→ 출력되는 URL을 n8n Webhook API에 등록하면 자동화 가능.

---

# 💬 CLI Usage

## 1) 프로필 → 키워드 추출
```bash
python main.py profile "3년차 백엔드인데 LLM 데이터 분석가 하고 싶음"
```

JSON 출력:
```bash
python main.py profile "데이터 엔지니어, Python/SQL 잘함" --json
```

## 2) 프로필 기반 크롤링
```bash
python main.py crawl --profile "데이터 분석가" --pages 3 --delay 1.0 --export-csv
```

## 3) 벡터 DB 구축
```bash
python main.py embed --limit 500
```

---

# 🧠 RAG Search Example

```python
from career_matcher.retriever.rag_retriever import RerankedJobRetriever

retriever = RerankedJobRetriever(fetch_k=20, top_n=5)
docs = retriever.get_relevant_documents("ML Ops 경력 포지션 추천해줘")

for d in docs:
    print(d.metadata["company"], d.page_content[:200])
```

---

# 🧪 Development

### Install dependencies
```
pip install -r requirements.txt
```

### Run specific components
```
python main.py crawl ...
python main.py embed ...
streamlit run career_matcher/app/streamlit_app.py
```

---

# 📂 Folder Structure

```
career_matcher/
 ├─ crawler/
 │   ├─ crawler.py        # Saramin spider
 │   └─ storage.py        # SQLite/CSV
 ├─ processing/
 │   └─ keyword_parser.py # Profile → Keywords
 ├─ embedding/
 │   └─ vector_pipeline.py
 ├─ retriever/
 │   └─ rag_retriever.py
 ├─ app/
 │   ├─ cli.py
 │   └─ streamlit_app.py
docker/
tests/
main.py
docker-compose.yml
cloudflare_tunnel.sh
```

---

# 🧩 n8n Integration (Optional But Powerful)

### 추천 API 자동화 플로우
1. Cloudflare Tunnel URL 확보  
2. n8n Webhook Trigger 생성  
3. profile 입력 받기  
4. `main.py profile` → keywords  
5. `main.py crawl` → 최신 공고 DB 업데이트  
6. `main.py embed` → vector refresh  
7. RAG Retriever → 추천 Job 리스트 출력  

→ 무료 AI + 무료 인프라 기반 **자동 커리어 추천 시스템** 구축 가능.

---

# ⚠️ Legal Note

이 프로젝트는 **연구/학습용 목적으로만 사용**해야 합니다.  
데이터는 Saramin의 robots.txt, 이용약관을 반드시 준수하세요.

---

# 🏷 License  
MIT

