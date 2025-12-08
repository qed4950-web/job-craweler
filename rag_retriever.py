"""
벡터 DB + BGE reranker 기반 Retriever 헬퍼
"""

from typing import Optional

from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_community.cross_encoders import HuggingFaceCrossEncoder
from langchain.retrievers import ContextualCompressionRetriever
from langchain.retrievers.document_compressors import CrossEncoderReranker

VECTOR_DIR = "career_matcher/vector_db"
COLLECTION_NAME = "career_jobs"
EMBED_MODEL = "dragonkue/multilingual-e5-small-ko"
RERANKER_MODEL = "BAAI/bge-reranker-large"


def load_embeddings():
    return HuggingFaceEmbeddings(
        model_name=EMBED_MODEL,
        encode_kwargs={"normalize_embeddings": True},
    )


def load_vectorstore(persist_directory: str = VECTOR_DIR):
    embeddings = load_embeddings()
    return Chroma(
        collection_name=COLLECTION_NAME,
        persist_directory=persist_directory,
        embedding_function=embeddings,
    )


def build_reranked_retriever(
    persist_directory: str = VECTOR_DIR,
    fetch_k: int = 20,
    top_n: int = 5,
    reranker_model: str = RERANKER_MODEL,
) -> ContextualCompressionRetriever:
    vectordb = load_vectorstore(persist_directory=persist_directory)
    retriever = vectordb.as_retriever(search_kwargs={"k": fetch_k})
    cross_encoder = HuggingFaceCrossEncoder(model_name=reranker_model)
    reranker = CrossEncoderReranker(model=cross_encoder, top_n=top_n)
    return ContextualCompressionRetriever(
        base_compressor=reranker,
        base_retriever=retriever,
    )


def demo(query: str, persist_directory: str = VECTOR_DIR):
    retriever = build_reranked_retriever(persist_directory=persist_directory)
    docs = retriever.get_relevant_documents(query)
    for idx, doc in enumerate(docs, start=1):
        title = doc.metadata.get("title", "제목 없음")
        print(f"Top {idx} - {title}")
        print(doc.page_content.splitlines()[0:4])
        print("---")


if __name__ == "__main__":
    sample_query = "LLM 경험 있는 데이터 엔지니어 포지션 추천해줘"
    demo(sample_query)
