from __future__ import annotations

import re
from typing import Any, Dict


class LatexRenderError(Exception):
    pass


class LatexRenderer:
    """
    Простой рендерер LaTeX-шаблонов.

    Поддерживает плейсхолдеры вида:
        {{ field_name }}

    Пример:
        template = "Дата: {{ date }}"
        context = {"date": "24.03.2026"}

    Результат:
        "Дата: 24.03.2026"
    """

    _pattern = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")

    def render(self, template_latex: str, context: Dict[str, Any]) -> str:
        if not isinstance(template_latex, str) or not template_latex.strip():
            raise LatexRenderError("template_latex must be a non-empty string.")

        if not isinstance(context, dict):
            raise LatexRenderError("context must be a dictionary.")

        def replace(match: re.Match[str]) -> str:
            key = match.group(1)
            value = context.get(key, "")
            return self._to_latex_string(value)

        return self._pattern.sub(replace, template_latex)

    def inject_document_body(
        self,
        template_latex: str,
        body: str,
        placeholder: str = "{{ document_body }}",
    ) -> str:
        if not isinstance(template_latex, str) or not template_latex.strip():
            raise LatexRenderError("template_latex must be a non-empty string.")

        if not isinstance(body, str):
            raise LatexRenderError("body must be a string.")

        if placeholder not in template_latex:
            raise LatexRenderError(
                f"Placeholder '{placeholder}' not found in template."
            )

        return template_latex.replace(placeholder, body)

    @staticmethod
    def _to_latex_string(value: Any) -> str:
        if value is None:
            return ""
        return str(value)


_default_renderer: LatexRenderer | None = None


def init_renderer() -> LatexRenderer:
    global _default_renderer
    _default_renderer = LatexRenderer()
    return _default_renderer


def get_renderer() -> LatexRenderer:
    if _default_renderer is None:
        _default_renderer_local = LatexRenderer()
        return _default_renderer_local
    return _default_renderer


def render_template(template_latex: str, context: Dict[str, Any]) -> str:
    return get_renderer().render(template_latex=template_latex, context=context)


def inject_document_body(
    template_latex: str,
    body: str,
    placeholder: str = "{{ document_body }}",
) -> str:
    return get_renderer().inject_document_body(
        template_latex=template_latex,
        body=body,
        placeholder=placeholder,
    )