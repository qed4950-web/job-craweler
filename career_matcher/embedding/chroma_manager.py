from pathlib import Path
from typing import Optional

import chromadb

from career_matcher.configs import settings


def get_chroma_client(persist_dir: Optional[Path] = None) -> chromadb.PersistentClient:
    persist_dir = persist_dir or settings.VECTOR_DB_DIR
    persist_dir.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(persist_dir))


def get_collection():
    client = get_chroma_client()
    return client.get_or_create_collection(name=settings.CHROMA_COLLECTION_NAME)
