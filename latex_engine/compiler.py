from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path


logger = logging.getLogger(__name__)


class LatexCompilationError(Exception):
    pass


class LatexCompiler:
    def __init__(
        self,
        output_dir: str | Path = "storage/generated",
        temp_dir: str | Path = "storage/temp",
        tectonic_binary: str = "tectonic",
    ) -> None:
        self.output_dir = Path(output_dir)
        self.temp_dir = Path(temp_dir)
        self.tectonic_binary = tectonic_binary

        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def compile(self, latex_code: str, session_id: str, version: int) -> dict:
        if not isinstance(latex_code, str) or not latex_code.strip():
            raise LatexCompilationError("LaTeX code is empty.")

        safe_session_id = self._sanitize_name(session_id)
        if not safe_session_id:
            raise LatexCompilationError("Session id is invalid after sanitization.")

        if not isinstance(version, int) or version < 1:
            raise LatexCompilationError("Version must be an integer >= 1.")

        work_dir = self.temp_dir / safe_session_id / f"v{version}"
        work_dir.mkdir(parents=True, exist_ok=True)

        tex_filename = f"{safe_session_id}_v{version}.tex"
        pdf_filename = f"{safe_session_id}_v{version}.pdf"

        tex_path = work_dir / tex_filename
        intermediate_pdf_path = work_dir / pdf_filename
        final_pdf_path = self.output_dir / pdf_filename

        tex_path.write_text(latex_code, encoding="utf-8")
        logger.info(
            "LaTeX compilation started | session_id=%s | version=%s | tex_path=%s | output_pdf=%s",
            safe_session_id,
            version,
            tex_path,
            final_pdf_path,
        )

        self._run_tectonic(
            tex_path=tex_path,
            work_dir=work_dir,
        )

        if not intermediate_pdf_path.exists():
            raise LatexCompilationError(
                f"Tectonic completed without producing PDF: {intermediate_pdf_path}"
            )

        shutil.copy2(intermediate_pdf_path, final_pdf_path)
        logger.info(
            "LaTeX compilation finished | session_id=%s | version=%s | pdf_path=%s",
            safe_session_id,
            version,
            final_pdf_path,
        )

        return {
            "tex_path": str(tex_path.resolve()),
            "pdf_path": str(final_pdf_path.resolve()),
        }

    def _run_tectonic(self, tex_path: Path, work_dir: Path) -> None:
        command = [
            self.tectonic_binary,
            str(tex_path.name),
            "--outdir",
            str(work_dir),
            "--synctex",
            "--keep-logs",
        ]

        try:
            result = subprocess.run(
                command,
                cwd=work_dir,
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError as exc:
            raise LatexCompilationError(
                f"Tectonic binary not found: {self.tectonic_binary}"
            ) from exc
        except Exception as exc:
            raise LatexCompilationError(f"Failed to run Tectonic: {exc}") from exc

        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            stdout = (result.stdout or "").strip()
            log_message = stderr or stdout or "Unknown Tectonic error."
            logger.error(
                "Tectonic failed | tex_path=%s | returncode=%s | message=%s",
                tex_path,
                result.returncode,
                log_message,
            )
            raise LatexCompilationError(
                f"LaTeX compilation failed with code {result.returncode}: {log_message}"
            )

    @staticmethod
    def _sanitize_name(value: str) -> str:
        allowed = []
        for ch in value.strip():
            if ch.isalnum() or ch in {"-", "_"}:
                allowed.append(ch)
            else:
                allowed.append("_")

        sanitized = "".join(allowed).strip("_")
        while "__" in sanitized:
            sanitized = sanitized.replace("__", "_")
        return sanitized
