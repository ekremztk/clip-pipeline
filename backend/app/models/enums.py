from enum import Enum

class JobStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    ANALYZING = "analyzing"
    CUTTING = "cutting"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"

class ContentType(str, Enum):
    REVELATION = "revelation"
    DEBATE = "debate"
    HUMOR = "humor"
    INSIGHT = "insight"
    EMOTIONAL = "emotional"
    CONTROVERSIAL = "controversial"
    STORYTELLING = "storytelling"
    CELEBRITY_CONFLICT = "celebrity_conflict"
    HOT_TAKE = "hot_take"
    FUNNY_REACTION = "funny_reaction"
    UNEXPECTED_ANSWER = "unexpected_answer"
    RELATABLE_MOMENT = "relatable_moment"
    EDUCATIONAL_INSIGHT = "educational_insight"

class ClipStrategyRole(str, Enum):
    LAUNCH = "launch"
    VIRAL = "viral"
    FAN_SERVICE = "fan_service"
    CONTEXT_BUILDER = "context_builder"

class FeedbackStatus(str, Enum):
    PENDING = "pending"
    PRELIMINARY_48H = "preliminary_48h"
    FINAL_7D = "final_7d"

class OnboardingStatus(str, Enum):
    SETUP = "setup"
    CONNECTING = "connecting"
    SCANNING = "scanning"
    ANALYZING = "analyzing"
    READY = "ready"

class StepStatus(str, Enum):
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"

class SignalPriority(str, Enum):
    TRIPLE = "TRIPLE"
    DUAL = "DUAL"
    SINGLE = "SINGLE"
