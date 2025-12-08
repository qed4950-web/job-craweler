import argparse
import os
import sqlite3
from typing import List, Optional

from langchain.docstore.document import Document
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma

DB_PATH = "career_matcher/jobs.db"
VECTOR_DIR = "career_matcher/vector_db"
COLLECTION_NAME = "career_jobs"


def fetch_job_documents(limit: Optional[int] = None) -> List[Document]:
    conn = sqlite3.connect(DB_PATH)
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


def build_vector_store(documents: List[Document], persist_directory: str = VECTOR_DIR):
    if not documents:
        raise ValueError("벡터화할 문서가 없습니다. 먼저 crawler로 데이터를 수집하세요.")

    os.makedirs(persist_directory, exist_ok=True)
    embeddings = HuggingFaceEmbeddings(
        model_name="dragonkue/multilingual-e5-small-ko",
        encode_kwargs={"normalize_embeddings": True},
    )
    vectordb = Chroma.from_documents(
        documents=documents,
        embedding=embeddings,
        persist_directory=persist_directory,
        collection_name=COLLECTION_NAME,
    )
    vectordb.persist()
    return vectordb


def main():
    parser = argparse.ArgumentParser(description="job_postings DB를 임베딩하여 벡터 DB로 저장합니다.")
    parser.add_argument("--limit", type=int, default=None, help="처리할 문서 수 제한")
    parser.add_argument("--persist-dir", default=VECTOR_DIR, help="Chroma persist 경로")
    args = parser.parse_args()

    docs = fetch_job_documents(limit=args.limit)
    print(f"[vector_pipeline] fetched {len(docs)} documents.")
    build_vector_store(docs, persist_directory=args.persist_dir)
    print(f"[vector_pipeline] vector store saved to {args.persist_dir}")


if __name__ == "__main__":
    main()
