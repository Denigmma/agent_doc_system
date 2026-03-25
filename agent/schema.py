from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class MessageRole(str, Enum):
    USER = "user"
    AGENT = "agent"
    SYSTEM = "system"
    PROCESSING = "processing"


class SessionStatus(str, Enum):
    EMPTY = "empty"
    DRAFT = "draft"
    GENERATED = "generated"
    REVISED = "revised"
    ERROR = "error"


@dataclass
class ChatMessage:
    role: MessageRole
    content: str


@dataclass
class TemplateShortInfo:
    template_id: str
    name: str
    description: str
    keywords: List[str] = field(default_factory=list)


@dataclass
class TemplateSelectionResult:
    template_id: str
    use_rag: bool = False
    use_web: bool = False
    rag_queries: List[str] = field(default_factory=list)
    web_queries: List[str] = field(default_factory=list)
    reasoning: Optional[str] = None


@dataclass
class RetrievalResult:
    source: str  # "rag" | "web"
    query: str
    content: str


@dataclass
class GeneratedArtifact:
    latex_code: str
    tex_path: Optional[str] = None
    pdf_path: Optional[str] = None


@dataclass
class RevisionPlan:
    needs_rag: bool = False
    needs_web: bool = False
    rag_queries: List[str] = field(default_factory=list)
    web_queries: List[str] = field(default_factory=list)
    edit_instruction: Optional[str] = None
    reasoning: Optional[str] = None


@dataclass
class SessionState:
    session_id: str
    status: SessionStatus = SessionStatus.EMPTY

    original_user_request: Optional[str] = None
    current_template_id: Optional[str] = None
    current_template_name: Optional[str] = None
    current_template_description: Optional[str] = None
    current_template_latex: Optional[str] = None

    current_latex: Optional[str] = None
    current_tex_path: Optional[str] = None
    current_pdf_path: Optional[str] = None

    retrieval_results: List[RetrievalResult] = field(default_factory=list)
    message_history: List[ChatMessage] = field(default_factory=list)

    version: int = 0
    last_error: Optional[str] = None

    def is_empty(self) -> bool:
        return self.status == SessionStatus.EMPTY or self.current_latex is None


@dataclass
class AgentResponse:
    message: str
    success: bool
    pdf_ready: bool = False
    pdf_path: Optional[str] = None
    tex_path: Optional[str] = None
    latex_code: Optional[str] = None
    template_id: Optional[str] = None
    version: Optional[int] = None
    error: Optional[str] = None
    processing_steps: List[str] = field(default_factory=list)


@dataclass
class LLMJsonResult:
    raw_text: str
    parsed: Dict[str, Any]
