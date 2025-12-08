import argparse
import sqlite3
from typing import List, Optional

from langchain.docstore.document import Document
from langchain_community.vectorstores import Chroma

from career_matcher.configs import settings
from career_matcher.embedding.embedding_models import get_embedding_model


def fetch_job_documents(limit: Optional[int] = None) -> List[Document]:
    conn = sqlite3.connect(settings.SQLITE_PATH)
    query = (
        "SELECT job_id, title, company, location, career, education, job_category, skills, summary, url "
        "FROM job_postings "
        "ORDER BY scraped_at DESC"
    )
    if limit:
        query += f" LIMIT {int(limit)}"
    rows = conn.execute(query).fetchall()
    conn.close()

    docs: List[Document] = []
    for row in rows:
        job_id, title, company, location, career, education, job_category, skills, summary, url = row
        parts = [
            f"제목: {title}",
            f"회사: {company}",
            f"근무지: {location}",
            f"경력/학력: {career} / {education}",
            f"직무 카테고리: {job_category}",
            f"요구 스킬: {skills}",
            f"요약: {summary or '요약 없음'}",
            f"링크: {url}",
        ]
        content = "\n".join(parts)
        docs.append(Document(page_content=content, metadata={"job_id": job_id, "title": title}))
    return docs


def build_vector_store(documents: List[Document], persist_directory: Optional[str] = None):
    if not documents:
        raise ValueError("벡터화할 문서가 없습니다. 먼저 crawler로 데이터를 수집하세요.")

    persist_directory = persist_directory or str(settings.VECTOR_DB_DIR)
    embeddings = get_embedding_model()
    vectordb = Chroma.from_documents(
        documents=documents,
        embedding=embeddings,
        persist_directory=persist_directory,
        collection_name=settings.CHROMA_COLLECTION_NAME,
    )
    vectordb.persist()
    return vectordb


def main():
    parser = argparse.ArgumentParser(description="job_postings DB를 임베딩하여 벡터 DB로 저장합니다.")
    parser.add_argument("--limit", type=int, default=None, help="처리할 문서 수 제한")
    parser.add_argument("--persist-dir", default=str(settings.VECTOR_DB_DIR), help="Chroma persist 경로")
    args = parser.parse_args()

    docs = fetch_job_documents(limit=args.limit)
    print(f"[vector_pipeline] fetched {len(docs)} documents.")
    build_vector_store(docs, persist_directory=args.persist_dir)
    print(f"[vector_pipeline] vector store saved to {args.persist_dir}")


if __name__ == "__main__":
    main()
