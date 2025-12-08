from functools import lru_cache

from langchain_community.embeddings import HuggingFaceEmbeddings
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from career_matcher.configs import settings


@lru_cache(maxsize=1)
def get_embedding_model() -> HuggingFaceEmbeddings:
    return HuggingFaceEmbeddings(
        model_name=settings.EMBEDDING_MODEL_NAME,
        encode_kwargs={"normalize_embeddings": True},
    )


@lru_cache(maxsize=1)
def get_reranker_model():
    model = AutoModelForSequenceClassification.from_pretrained(settings.RERANKER_MODEL_NAME)
    tokenizer = AutoTokenizer.from_pretrained(settings.RERANKER_MODEL_NAME)
    return model, tokenizer
