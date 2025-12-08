FROM python:3.11-slim

WORKDIR /app
COPY . /app

RUN pip install --no-cache-dir streamlit \
    chromadb langchain sentence-transformers \
    transformers huggingface-hub fastapi pydantic

EXPOSE 8502

CMD ["streamlit", "run", "career_matcher/app/streamlit_app.py", "--server.address=0.0.0.0", "--server.port=8502"]
