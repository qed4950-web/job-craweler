from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class JobPosting:
    job_id: str
    title: str
    company: str
    location: str
    salary: str
    job_category: str
    career: str
    education: str
    due_date: str
    url: str
    skills: str = ""
    posted_at: Optional[str] = None
    closes_at: Optional[str] = None
    summary: Optional[str] = None
    scraped_at: datetime = field(default_factory=datetime.utcnow)
