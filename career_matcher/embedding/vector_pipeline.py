import argparse
import hashlib
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Set

from langchain.docstore.document import Document
from langchain_community.vectorstores import Chroma

from career_matcher.configs import settings
from career_matcher.embedding.embedding_models import get_embedding_model


def ensure_persist_dir(path_str: str) -> str:
    path = Path(path_str)
    if path.exists() and not path.is_dir():
        raise RuntimeError(f"persist-dir must be a directory: {path}")
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


def compute_hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def fetch_job_documents(limit: Optional[int] = None) -> List[Document]:
    conn = sqlite3.connect(settings.SQLITE_PATH)
    query = (
        "SELECT job_id, title, summary, skills "
        "FROM job_postings "
        "ORDER BY scraped_at DESC"
    )
    if limit:
        query += f" LIMIT {int(limit)}"

    rows = conn.execute(query).fetchall()
    conn.close()

    docs: List[Document] = []
    for job_id, title, summary, skills in rows:
        # 요약 없는 문서는 임베딩 제외 (retriever 품질을 위해)
        if not summary:
            continue
        content = f"{title}\n{summary}\n{skills or ''}"
        docs.append(
            Document(
                page_content=content,
                metadata={"id": job_id, "hash": compute_hash(content)},
            )
        )
    return docs


def load_or_create_chroma(persist_directory: str):
    """기존 컬렉션을 로드하거나 없으면 생성한다."""
    embeddings = get_embedding_model()
    return Chroma(
        persist_directory=persist_directory,
        embedding_function=embeddings,
        collection_name=settings.CHROMA_COLLECTION_NAME,
    )


def get_existing_id_hash_map(vectordb) -> Dict[str, str]:
    """기존 vectorstore에서 이미 임베딩된 job_id -> hash 매핑을 가져온다."""
    try:
        data = vectordb.get(include=["metadatas"])
        ids = data.get("ids", [])
        metas = data.get("metadatas", [])
        mapping: Dict[str, str] = {}
        for vid, meta in zip(ids, metas):
            if not meta:
                continue
            mid = meta.get("id")
            mhash = meta.get("hash")
            if mid:
                mapping[mid] = mhash or ""
        return mapping
    except Exception:
        return {}


def main():
    parser = argparse.ArgumentParser(description="job_postings DB를 임베딩해 Chroma 벡터DB로 추가 저장")
    parser.add_argument("--limit", type=int, default=None, help="처리할 문서 수 제한")
    parser.add_argument("--persist-dir", default=str(settings.VECTOR_DB_DIR), help="Chroma persist 경로")
    args = parser.parse_args()

    persist_dir = ensure_persist_dir(args.persist_dir)

    docs = fetch_job_documents(limit=args.limit)
    print(f"[vector_pipeline] fetched {len(docs)} docs (summary 존재 기준).")

    vectordb = load_or_create_chroma(persist_dir)
    existing_map = get_existing_id_hash_map(vectordb)

    new_docs: List[Document] = []
    for d in docs:
        doc_id = d.metadata.get("id")
        doc_hash = d.metadata.get("hash")
        if doc_id is None:
            continue
        if doc_id not in existing_map or existing_map.get(doc_id) != doc_hash:
            new_docs.append(d)

    print(f"[vector_pipeline] new/updated docs to embed: {len(new_docs)} (existing={len(existing_map)})")

    if not new_docs:
        print("[vector_pipeline] no new documents. done.")
        return

    # Batch embed then add (faster than add_documents for large sets)
    embedder = get_embedding_model()
    texts = [d.page_content for d in new_docs]
    metas = [d.metadata for d in new_docs]
    ids = [m["id"] for m in metas]
    vectors = embedder.embed_documents(texts)

    vectordb._collection.add(
        embeddings=vectors,
        documents=texts,
        metadatas=metas,
        ids=ids,
    )
    vectordb.persist()

    print(f"[vector_pipeline] updated vector store saved to {persist_dir}")


if __name__ == "__main__":
    main()
