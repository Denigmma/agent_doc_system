from __future__ import annotations

import logging
from typing import Optional

from neuro_web_search.main import ai_overview_pipeline


logger = logging.getLogger(__name__)


class WebSearchToolError(Exception):
    pass


class WebSearchTool:
    def search(self, query: str) -> str:
        if not isinstance(query, str) or not query.strip():
            raise WebSearchToolError("query must be a non-empty string.")

        logger.info("Web search started | query=%s", query.strip())
        try:
            result = ai_overview_pipeline(query.strip())
        except Exception as exc:
            logger.exception("Web search failed | query=%s", query.strip())
            raise WebSearchToolError(f"Web search failed: {exc}") from exc

        if result is None:
            logger.info("Web search finished | query=%s | empty result", query.strip())
            return ""

        if isinstance(result, str):
            normalized = result.strip()
            logger.info("Web search finished | query=%s | response=%s", query.strip(), normalized[:300])
            return normalized

        normalized = str(result).strip()
        logger.info("Web search finished | query=%s | response=%s", query.strip(), normalized[:300])
        return normalized


_default_web_search_tool: Optional[WebSearchTool] = None


def init_web_search_tool() -> WebSearchTool:
    global _default_web_search_tool
    _default_web_search_tool = WebSearchTool()
    return _default_web_search_tool


def get_web_search_tool() -> WebSearchTool:
    global _default_web_search_tool
    if _default_web_search_tool is None:
        _default_web_search_tool = WebSearchTool()
    return _default_web_search_tool


def search_web(query: str) -> str:
    return get_web_search_tool().search(query)
