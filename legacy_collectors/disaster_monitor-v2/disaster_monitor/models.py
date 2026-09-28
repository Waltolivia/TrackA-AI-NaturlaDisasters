from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

@dataclass
class NormalizedAlert:
    source: str
    source_id: str
    event_type: str
    headline: str
    severity: str
    urgency: str
    certainty: str
    status: str
    sent_at: str | None
    expires_at: str | None
    area_desc: str
    geometry: dict[str, Any] | None
    references: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)
    source_event_id: str | None = None

    @property
    def observed_at(self) -> str:
        return datetime.now(timezone.utc).isoformat()
