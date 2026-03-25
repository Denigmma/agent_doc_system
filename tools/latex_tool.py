from __future__ import annotations

from pathlib import Path
from typing import Optional

from latex_engine.compiler import LatexCompiler, LatexCompilationError


class LatexToolError(Exception):
    pass


class LatexTool:
    def __init__(
        self,
        output_dir: str | Path = "storage/generated",
        temp_dir: str | Path = "storage/temp",
        tectonic_binary: str = "tectonic",
    ) -> None:
        self.compiler = LatexCompiler(
            output_dir=output_dir,
            temp_dir=temp_dir,
            tectonic_binary=tectonic_binary,
        )

    def compile_latex(
        self,
        latex_code: str,
        session_id: str,
        version: int,
    ) -> dict:
        if not isinstance(latex_code, str) or not latex_code.strip():
            raise LatexToolError("latex_code must be a non-empty string.")

        if not isinstance(session_id, str) or not session_id.strip():
            raise LatexToolError("session_id must be a non-empty string.")

        if not isinstance(version, int) or version < 1:
            raise LatexToolError("version must be an integer >= 1.")

        try:
            result = self.compiler.compile(
                latex_code=latex_code,
                session_id=session_id.strip(),
                version=version,
            )
        except LatexCompilationError as exc:
            raise LatexToolError(str(exc)) from exc

        return {
            "tex_path": result["tex_path"],
            "pdf_path": result["pdf_path"],
        }


_default_latex_tool: Optional[LatexTool] = None


def init_latex_tool(
    output_dir: str | Path = "storage/generated",
    temp_dir: str | Path = "storage/temp",
    tectonic_binary: str = "tectonic",
) -> LatexTool:
    global _default_latex_tool
    _default_latex_tool = LatexTool(
        output_dir=output_dir,
        temp_dir=temp_dir,
        tectonic_binary=tectonic_binary,
    )
    return _default_latex_tool


def get_latex_tool() -> LatexTool:
    if _default_latex_tool is None:
        raise LatexToolError(
            "Latex tool is not initialized. "
            "Call init_latex_tool(...) first."
        )
    return _default_latex_tool


def compile_latex(latex_code: str, session_id: str, version: int) -> dict:
    return get_latex_tool().compile_latex(
        latex_code=latex_code,
        session_id=session_id,
        version=version,
    )