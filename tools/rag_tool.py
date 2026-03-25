from __future__ import annotations

import logging
from typing import Optional

from RAG.rag_main import answer_query


logger = logging.getLogger(__name__)


class RagToolError(Exception):
    pass


class RagTool:
    def search(self, query: str) -> str:
        if not isinstance(query, str) or not query.strip():
            raise RagToolError("query must be a non-empty string.")

        logger.info("RAG search started | query=%s", query.strip())
        try:
            result = answer_query(query.strip())
        except Exception as exc:
            logger.exception("RAG search failed | query=%s", query.strip())
            raise RagToolError(f"RAG search failed: {exc}") from exc

        if result is None:
            logger.info("RAG search finished | query=%s | empty result", query.strip())
            return ""

        if isinstance(result, str):
            normalized = result.strip()
            logger.info("RAG search finished | query=%s | response=%s", query.strip(), normalized[:300])
            return normalized

        normalized = str(result).strip()
        logger.info("RAG search finished | query=%s | response=%s", query.strip(), normalized[:300])
        return normalized


_default_rag_tool: Optional[RagTool] = None


def init_rag_tool() -> RagTool:
    global _default_rag_tool
    _default_rag_tool = RagTool()
    return _default_rag_tool


def get_rag_tool() -> RagTool:
    global _default_rag_tool
    if _default_rag_tool is None:
        _default_rag_tool = RagTool()
    return _default_rag_tool


def search_rag(query: str) -> str:
    return get_rag_tool().search(query)
