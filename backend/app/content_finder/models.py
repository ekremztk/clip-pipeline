from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class QueryGenerationResult(BaseModel):
    query: str
    strategy: str  # "topic" | "guest" | "niche_deep" | "trending" | "evergreen"
    expected_content: str
    priority: int = Field(ge=1, le=5, default=3)


class YouTubeVideoResult(BaseModel):
    youtube_video_id: str
    title: str
    description: Optional[str] = None
    channel_id: str
    channel_title: str
    duration_seconds: int
    published_at: Optional[datetime] = None
    view_count: int = 0
    like_count: int = 0
    comment_count: int = 0
    thumbnail_url: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    format_signal: bool = False
    detected_guest_name: Optional[str] = None


class QuickScores(BaseModel):
    topic_match: float = 5.0
    guest_potential: float = 5.0
    format_score: float = 5.0
    engagement: float = 5.0
    freshness: float = 5.0
    uniqueness: float = 8.0
    composite: float = 5.0


class DetectedMoment(BaseModel):
    type: str  # humor | revelation | debate | emotional | storytelling
    description: str
    approximate_location: str  # baslangi | erken-orta | orta | gec-orta | son
    strength: int = Field(ge=1, le=10, default=5)


class GuestAssessment(BaseModel):
    name: str
    charisma_level: int = Field(ge=1, le=10, default=5)
    humor_potential: int = Field(ge=1, le=10, default=5)
    storytelling_ability: int = Field(ge=1, le=10, default=5)
    controversial_potential: int = Field(ge=1, le=10, default=5)


class ConversationDynamics(BaseModel):
    energy_level: str = "medium"  # low | medium | high | variable
    chemistry: str = "decent"  # weak | decent | strong | electric
    format_type: str = "interview"  # interview | casual_chat | debate | monologue | panel


class DeepAnalysisResult(BaseModel):
    clip_potential_score: float = Field(ge=1, le=10, default=5)
    estimated_clip_count: int = 0
    detected_moments: list[DetectedMoment] = Field(default_factory=list)
    guest_assessment: Optional[GuestAssessment] = None
    conversation_dynamics: ConversationDynamics = Field(default_factory=ConversationDynamics)
    channel_fit_analysis: str = ""
    risk_factors: list[str] = Field(default_factory=list)
    selection_reasoning: str = ""


class WhySelected(BaseModel):
    summary: str
    key_reasons: list[str] = Field(default_factory=list)
    detected_moments: list[DetectedMoment] = Field(default_factory=list)
    risk_warnings: list[str] = Field(default_factory=list)


class DiscoveredContentPresentation(BaseModel):
    id: str
    video: YouTubeVideoResult
    scores: QuickScores
    deep_analysis: Optional[DeepAnalysisResult] = None
    final_score: float = 0.0
    why_selected: Optional[WhySelected] = None
    guest_info: Optional[GuestAssessment] = None
    status: str = "new"
    discovered_at: Optional[datetime] = None


class DiscoveryRunStatus(BaseModel):
    run_id: str
    status: str = "running"  # running | completed | failed
    channel_id: str = ""
    current_phase: str = ""  # F01 | F02 | F03 | F04 | F05 | F06
    queries_done: int = 0
    queries_total: int = 0
    videos_found: int = 0
    videos_analyzed: int = 0
    videos_total: int = 0
    recommendations_count: int = 0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
