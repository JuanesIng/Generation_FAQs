from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class IngestRequest(BaseModel):
    limit: int = Field(15000, ge=100, le=50000)
    since_days: int = Field(180, ge=1, le=365)


class IngestResponse(BaseModel):
    imported_records: int
    output_file: str


class EncodeRequest(BaseModel):
    texts: List[str]


class EncodeResponse(BaseModel):
    embeddings: List[List[float]]
    count: int


class ValidationStatus(str, Enum):
    approved = "approved"
    rejected = "rejected"
    needs_changes = "needs_changes"


class SuggestionResponse(BaseModel):
    id: str
    company_id: str
    company_name: Optional[str] = None
    question: str
    answer: str
    cluster_size: int
    support_examples: List[str]
    cluster_score: float


class SuggestionSummary(BaseModel):
    company_count: int
    cluster_count: int
    total_examples: int
    average_cluster_size: float
    silhouette_score: Optional[float]
    suggestions: List[SuggestionResponse]


class ValidationRequest(BaseModel):
    suggestion_id: str
    reviewer: str
    status: ValidationStatus
    notes: Optional[str] = None
    reviewed_at: Optional[datetime] = None


class ValidationResponse(BaseModel):
    suggestion_id: str
    reviewer: str
    status: ValidationStatus
    notes: Optional[str] = None
    reviewed_at: datetime