from pathlib import Path

# 프로젝트 루트와 패키지 루트를 계산
PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = PACKAGE_ROOT.parent

# 데이터/벡터 DB 기본 경로
DATA_DIR = PACKAGE_ROOT / "data"
CSV_DIR = DATA_DIR / "csv"
VECTOR_DB_DIR = DATA_DIR / "vector_db"
SQLITE_PATH = DATA_DIR / "jobs.db"

# 크롤러 기본 설정
MAX_JOB_COUNT = 300
JOBS_PER_PAGE = 40
DEFAULT_LIST_DELAY = 1.0
DEFAULT_SUMMARY_DELAY = 0.5
DEFAULT_MAX_PAGES = (MAX_JOB_COUNT + JOBS_PER_PAGE - 1) // JOBS_PER_PAGE

# 임베딩 / Reranker 설정
EMBEDDING_MODEL_NAME = "dragonkue/multilingual-e5-small-ko"
RERANKER_MODEL_NAME = "BAAI/bge-reranker-large"
CHROMA_COLLECTION_NAME = "career_jobs"
