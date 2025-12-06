from typing import List, Literal, Union
from pydantic import BaseModel, HttpUrl, field_validator


class AnalyzeIssueRequest(BaseModel):
    repo_url: HttpUrl
    issue_number: int


class IssueAnalysis(BaseModel):
    summary: str
    type: Literal["bug", "feature_request", "documentation", "question", "other"]
    priority_score: str  # e.g. "3 - Medium. Justification..."
    suggested_labels: List[str]
    potential_impact: str
    
    @field_validator('priority_score', mode='before')
    @classmethod
    def convert_priority_score(cls, v):
        """Convert integer priority scores to strings"""
        if isinstance(v, int):
            # Convert number to descriptive string
            descriptions = {
                1: "1 - Low priority",
                2: "2 - Low to Medium priority",
                3: "3 - Medium priority",
                4: "4 - High priority",
                5: "5 - Critical priority"
            }
            return descriptions.get(v, f"{v} - Priority level {v}")
        return str(v)
    
    @field_validator('suggested_labels', mode='before')
    @classmethod
    def ensure_list(cls, v):
        """Ensure suggested_labels is always a list"""
        if isinstance(v, str):
            return [v]
        if not isinstance(v, list):
            return []
        return v


class IssueData(BaseModel):
    title: str
    body: str
    comments: List[str]


class AnalyzeIssueResponse(BaseModel):
    issue: IssueData
    analysis: IssueAnalysis