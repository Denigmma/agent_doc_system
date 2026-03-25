from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import List

from agent.schema import TemplateShortInfo


logger = logging.getLogger(__name__)


class TemplateToolError(Exception):
    pass


class TemplateNotFoundError(TemplateToolError):
    pass


class TemplateValidationError(TemplateToolError):
    pass


class TemplateRepository:
    """
    Репозиторий шаблонов документов.

    Ожидаемая структура:
    templates_db/
    ├── some_template/
    │   ├── meta.json
    │   └── template.tex
    ├── another_template/
    │   ├── meta.json
    │   └── template.tex


    Пример meta.json
{
  "template_id": "technical_report",
  "name": "Технический отчет",
  "description": "Шаблон технического отчета по проверке оборудования",
  "keywords": ["отчет", "проверка", "оборудование", "диагностика"],
  "required_fields": ["date", "equipment_name", "work_description", "result"]
}
    """

    def __init__(self, base_dir: str | Path) -> None:
        self.base_dir = Path(base_dir)

        if not self.base_dir.exists():
            raise TemplateToolError(f"Templates directory does not exist: {self.base_dir}")

        if not self.base_dir.is_dir():
            raise TemplateToolError(f"Templates path is not a directory: {self.base_dir}")

        logger.info("Template repository initialized | base_dir=%s", self.base_dir)

    def list_templates(self) -> List[TemplateShortInfo]:
        templates: List[TemplateShortInfo] = []

        for template_dir in sorted(self.base_dir.iterdir()):
            if not template_dir.is_dir():
                continue

            try:
                meta = self._load_meta(template_dir)
                template_id = self._resolve_template_id(template_dir, meta)

                templates.append(
                    TemplateShortInfo(
                        template_id=template_id,
                        name=str(meta["name"]),
                        description=str(meta["description"]),
                        keywords=self._normalize_keywords(meta.get("keywords", [])),
                    )
                )
            except TemplateToolError:
                # Пропускаем битые шаблоны, чтобы один плохой шаблон не ломал весь список
                logger.warning("Skipping invalid template directory: %s", template_dir)
                continue

        logger.info("Template list built | count=%s", len(templates))
        return templates

    def load_template(self, template_id: str) -> dict:
        template_dir = self._find_template_dir(template_id)
        if template_dir is None:
            raise TemplateNotFoundError(f"Template not found: {template_id}")

        meta = self._load_meta(template_dir)
        latex = self._load_template_latex(template_dir)

        resolved_template_id = self._resolve_template_id(template_dir, meta)
        logger.info(
            "Loaded template | template_id=%s | template_dir=%s | latex_length=%s",
            resolved_template_id,
            template_dir,
            len(latex),
        )

        return {
            "template_id": resolved_template_id,
            "name": str(meta["name"]),
            "description": str(meta["description"]),
            "keywords": self._normalize_keywords(meta.get("keywords", [])),
            "required_fields": self._normalize_str_list(meta.get("required_fields", [])),
            "latex": latex,
            "template_dir": str(template_dir),
            "meta_path": str(template_dir / "meta.json"),
            "template_path": str(template_dir / "template.tex"),
        }

    def get_template_manifest(self) -> List[dict]:
        manifest: List[dict] = []

        for item in self.list_templates():
            manifest.append(
                {
                    "template_id": item.template_id,
                    "name": item.name,
                    "description": item.description,
                    "keywords": item.keywords,
                }
            )

        return manifest

    def _find_template_dir(self, template_id: str) -> Path | None:
        normalized_requested = template_id.strip()

        for template_dir in sorted(self.base_dir.iterdir()):
            if not template_dir.is_dir():
                continue

            try:
                meta = self._load_meta(template_dir)
                resolved_template_id = self._resolve_template_id(template_dir, meta)

                if resolved_template_id == normalized_requested:
                    return template_dir
            except TemplateToolError:
                continue

        return None

    def _load_meta(self, template_dir: Path) -> dict:
        meta_path = template_dir / "meta.json"
        if not meta_path.exists():
            raise TemplateValidationError(f"meta.json not found in {template_dir}")

        try:
            with meta_path.open("r", encoding="utf-8") as f:
                meta = json.load(f)
        except json.JSONDecodeError as exc:
            raise TemplateValidationError(f"Invalid JSON in {meta_path}: {exc}") from exc

        if not isinstance(meta, dict):
            raise TemplateValidationError(f"meta.json must contain an object: {meta_path}")

        self._validate_meta(meta, template_dir)
        return meta

    def _load_template_latex(self, template_dir: Path) -> str:
        template_path = template_dir / "template.tex"
        if not template_path.exists():
            raise TemplateValidationError(f"template.tex not found in {template_dir}")

        latex = template_path.read_text(encoding="utf-8").strip()
        if not latex:
            raise TemplateValidationError(f"template.tex is empty in {template_dir}")

        return latex

    @staticmethod
    def _validate_meta(meta: dict, template_dir: Path) -> None:
        required_keys = ["name", "description"]

        for key in required_keys:
            value = meta.get(key)
            if not isinstance(value, str) or not value.strip():
                raise TemplateValidationError(
                    f"Field '{key}' is required and must be a non-empty string in {template_dir / 'meta.json'}"
                )

        if "keywords" in meta and not isinstance(meta["keywords"], list):
            raise TemplateValidationError(
                f"Field 'keywords' must be a list in {template_dir / 'meta.json'}"
            )

        if "required_fields" in meta and not isinstance(meta["required_fields"], list):
            raise TemplateValidationError(
                f"Field 'required_fields' must be a list in {template_dir / 'meta.json'}"
            )

        if "template_id" in meta:
            template_id = meta["template_id"]
            if not isinstance(template_id, str) or not template_id.strip():
                raise TemplateValidationError(
                    f"Field 'template_id' must be a non-empty string in {template_dir / 'meta.json'}"
                )

    @staticmethod
    def _resolve_template_id(template_dir: Path, meta: dict) -> str:
        template_id = meta.get("template_id")
        if isinstance(template_id, str) and template_id.strip():
            return template_id.strip()
        return template_dir.name

    @staticmethod
    def _normalize_keywords(value: object) -> List[str]:
        return TemplateRepository._normalize_str_list(value)

    @staticmethod
    def _normalize_str_list(value: object) -> List[str]:
        if not isinstance(value, list):
            return []

        result: List[str] = []
        for item in value:
            if item is None:
                continue
            item_str = str(item).strip()
            if item_str:
                result.append(item_str)
        return result


_default_repository: TemplateRepository | None = None


def init_template_repository(base_dir: str | Path) -> TemplateRepository:
    global _default_repository
    _default_repository = TemplateRepository(base_dir=base_dir)
    return _default_repository


def get_template_repository() -> TemplateRepository:
    if _default_repository is None:
        raise TemplateToolError(
            "Template repository is not initialized. "
            "Call init_template_repository(base_dir) first."
        )
    return _default_repository


def list_templates() -> List[TemplateShortInfo]:
    return get_template_repository().list_templates()


def load_template(template_id: str) -> dict:
    return get_template_repository().load_template(template_id)


def get_template_manifest() -> List[dict]:
    return get_template_repository().get_template_manifest()
