from typing import Optional, Dict, List
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field

from app.models.enums import (
    JobStatus, 
    SignalPriority, 
    ClipStrategyRole, 
    ContentType, 
    StepStatus,
    FeedbackStatus,
    OnboardingStatus
)

class SpeakerInfo(BaseModel):
    role: str
    name: Optional[str] = None

class SpeakerConfirmRequest(BaseModel):
    speaker_map: Dict[str, SpeakerInfo]

class ClipCandidate(BaseModel):
    candidate_id: int
    timestamp: str
    reason: str
    signal: str
    strength: int = Field(ge=1, le=10)

class ClipScore(BaseModel):
    candidate_id: int
    recommended_start: float
    recommended_end: float
    duration_s: float
    hook_text: str
    standalone_score: float
    hook_score: float
    arc_score: float
    channel_fit_score: float
    content_type: str
    thinking_steps: List[str]
    needs_context_prefix: bool
    overall_confidence: float

class FusedSignalEntry(BaseModel):
    timestamp_start: float
    timestamp_end: float
    transcript: str
    sentiment_score: Optional[float] = None
    energy_level: Optional[float] = None
    visual_event: Optional[str] = None
    humor_type: Optional[str] = None
    priority: SignalPriority
    signals_count: int

class JobCreateRequest(BaseModel):
    video_title: str
    guest_name: Optional[str] = None
    channel_id: str = "speedy_cast"

class JobResponse(BaseModel):
    id: UUID
    status: JobStatus
    current_step: Optional[str] = None
    progress_pct: int
    clip_count: int
    error_message: Optional[str] = None
    created_at: datetime

class ClipResponse(BaseModel):
    id: UUID
    clip_index: int
    hook_text: Optional[str] = None
    content_type: Optional[str] = None
    confidence: Optional[float] = None
    standalone_score: Optional[float] = None
    hook_score: Optional[float] = None
    arc_score: Optional[float] = None
    clip_strategy_role: Optional[str] = None
    posting_order: Optional[int] = None
    suggested_title: Optional[str] = None
    video_landscape_path: Optional[str] = None
    file_url: Optional[str] = None
    duration_s: float
    created_at: datetime
