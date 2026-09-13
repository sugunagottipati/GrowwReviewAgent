from enum import StrEnum


class Sentiment(StrEnum):
    POSITIVE = "positive"
    MIXED = "mixed"
    NEGATIVE = "negative"


class RunStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
