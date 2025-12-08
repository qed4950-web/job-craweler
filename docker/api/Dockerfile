FROM python:3.11-slim

WORKDIR /app
COPY . /app

# 필수 패키지 설치
RUN pip install --no-cache-dir fastapi uvicorn \
    chromadb langchain sentence-transformers \
    transformers huggingface-hub \
    pydantic streamlit

EXPOSE 8000

CMD ["uvicorn", "career_matcher.api.server:app", "--host", "0.0.0.0", "--port", "8000"]
