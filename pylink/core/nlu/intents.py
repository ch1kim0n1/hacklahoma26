from dataclasses import dataclass, field
from typing import Dict, Any


@dataclass
class Intent:
    name: str
    entities: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    raw_text: str = ""
