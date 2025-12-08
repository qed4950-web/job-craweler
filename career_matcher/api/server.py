from fastapi import FastAPI

from career_matcher.api.recommend import router as recommend_router

app = FastAPI(
    title="CareerMatcher API",
    description="Job recommendation API with semantic + recency + skill + reranker",
    version="1.0.0",
)

app.include_router(recommend_router, prefix="/api")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "career_matcher.api.server:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
