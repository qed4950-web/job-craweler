from typing import List

from langchain.retrievers.document_compressors import CrossEncoderReranker
from langchain_community.cross_encoders import HuggingFaceCrossEncoder
from langchain_core.documents import Document

from career_matcher.configs import settings


def rerank_documents(docs: List[Document], query: str, top_n: int) -> List[Document]:
    if not docs:
        return []
    cross_encoder = HuggingFaceCrossEncoder(model_name=settings.RERANKER_MODEL_NAME)
    reranker = CrossEncoderReranker(model=cross_encoder, top_n=top_n)
    return reranker.compress_documents(documents=docs, query=query)
