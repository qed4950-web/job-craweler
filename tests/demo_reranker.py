"""
간단한 Reranker 데모 (벡터 DB + BGE Reranker)
"""

import sqlite3
from pathlib import Path
from typing import List

from langchain.docstore.document import Document
from langchain_community.vectorstores import Chroma
from langchain.retrievers import ContextualCompressionRetriever
from langchain.retrievers.document_compressors import CrossEncoderReranker
from langchain_community.cross_encoders import HuggingFaceCrossEncoder

from career_matcher.configs import settings
from career_matcher.embedding.embedding_models import get_embedding_model

DEMO_VECTOR_DIR = settings.VECTOR_DB_DIR / "demo"


def load_documents(limit: int = 200) -> List[Document]:
    conn = sqlite3.connect(settings.SQLITE_PATH)
    rows = conn.execute(
        "SELECT job_id, title, company, location, career, education, job_category, skills, summary, url "
        "FROM job_postings WHERE summary != '' LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()

    docs = []
    for row in rows:
        job_id, title, company, location, career, education, job_category, skills, summary, url = row
        content = f"""제목: {title}
회사: {company}
근무지: {location}
경력/학력: {career} / {education}
직무 카테고리: {job_category}
요구 스킬: {skills}
요약: {summary}
링크: {url}
"""
        docs.append(Document(page_content=content, metadata={"job_id": job_id, "title": title}))
    return docs


def build_vectorstore(documents: List[Document]):
    DEMO_VECTOR_DIR.mkdir(parents=True, exist_ok=True)
    embeddings = get_embedding_model()
    vectordb = Chroma.from_documents(
        documents=documents,
        embedding=embeddings,
        persist_directory=str(DEMO_VECTOR_DIR),
        collection_name="demo_jobs",
    )
    vectordb.persist()
    return vectordb


def main():
    docs = load_documents()
    if not docs:
        print("요약(summary)이 있는 문서가 없습니다. 먼저 --fetch-summary 옵션으로 크롤링하세요.")
        return
    vectordb = build_vectorstore(docs)

    retriever = vectordb.as_retriever(search_kwargs={"k": 20})
    cross_encoder = HuggingFaceCrossEncoder(model_name=settings.RERANKER_MODEL_NAME)
    reranker = CrossEncoderReranker(model=cross_encoder, top_n=5)
    compressed_retriever = ContextualCompressionRetriever(
        base_compressor=reranker,
        base_retriever=retriever,
    )

    query = "LLM 모델 최적화 경험 있는 머신러닝 엔지니어 포지션 찾고 싶어"
    results = compressed_retriever.get_relevant_documents(query)
    for idx, doc in enumerate(results, start=1):
        print(f"Top {idx}: {doc.metadata['title']}")
        print(doc.page_content[:200], "...\n")


if __name__ == "__main__":
    main()
