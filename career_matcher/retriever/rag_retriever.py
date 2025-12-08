"""
벡터 DB + BGE reranker 기반 Retriever 헬퍼
"""

from typing import List, Optional

from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document

from career_matcher.configs import settings
from career_matcher.embedding.embedding_models import get_embedding_model
from career_matcher.retriever.reranker import rerank_documents


class RerankedJobRetriever:
    def __init__(self, fetch_k: int = 20, top_n: int = 5, persist_directory: Optional[str] = None):
        self.fetch_k = fetch_k
        self.top_n = top_n
        self.persist_directory = persist_directory or str(settings.VECTOR_DB_DIR)
        self.embedding_model = get_embedding_model()
        self.vectordb = Chroma(
            collection_name=settings.CHROMA_COLLECTION_NAME,
            persist_directory=self.persist_directory,
            embedding_function=self.embedding_model,
        )

    def get_relevant_documents(self, query: str) -> List[Document]:
        retriever = self.vectordb.as_retriever(search_kwargs={"k": self.fetch_k})
        docs = retriever.get_relevant_documents(query)
        return rerank_documents(docs, query=query, top_n=self.top_n)


def demo(query: str, persist_directory: Optional[str] = None):
    retriever = RerankedJobRetriever(persist_directory=persist_directory)
    docs = retriever.get_relevant_documents(query)
    for idx, doc in enumerate(docs, start=1):
        title = doc.metadata.get("title", "제목 없음")
        print(f"Top {idx} - {title}")
        print(doc.page_content.splitlines()[0:4])
        print("---")


if __name__ == "__main__":
    sample_query = "LLM 경험 있는 데이터 엔지니어 포지션 추천해줘"
    demo(sample_query)
