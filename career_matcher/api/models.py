from typing import Optional

from pydantic import BaseModel


class ScoreModel(BaseModel):
    semantic: float
    recency: float
    skill: float
    combined: float


class JobResultModel(BaseModel):
    job_id: str
    title: Optional[str]
    company: Optional[str]
    location: Optional[str]
    url: Optional[str]
    skills: Optional[str]
    posted_at: Optional[str]
    due_date: Optional[str]
    summary: Optional[str]
    scores: ScoreModel
