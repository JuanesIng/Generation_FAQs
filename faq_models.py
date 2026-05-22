from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class CompanyInfo(BaseModel):
    id: str
    name: Optional[str] = None


class IngestRequest(BaseModel):
    limit: int = Field(15000, ge=100, le=50000)
    since_days: int = Field(180, ge=1, le=365)
    company_id: Optional[str] = None


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
    coherence_score: float
    answer_relevance: float


class SuggestionSummary(BaseModel):
    company_count: int
    cluster_count: int
    total_examples: int
    average_cluster_size: float
    avg_coherence_score: Optional[float]
    avg_answer_relevance: Optional[float]
    suggestions: List[SuggestionResponse]


class SuggestionEditRequest(BaseModel):
    question: str
    answer: str


class ValidationRequest(BaseModel):
    suggestion_id: str
    reviewer: str
    status: ValidationStatus
    notes: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    company_id: Optional[str] = None

class ValidationResponse(BaseModel):
    suggestion_id: str
    reviewer: str
    status: ValidationStatus
    notes: Optional[str] = None
    reviewed_at: datetime

class PromoteRequest(BaseModel):
    company_id: Optional[str] = None