from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Callable, List, Optional

from dotenv import load_dotenv
from openai import OpenAI

from .prompt_builder import (
    build_new_document_generation_prompt,
    build_revision_generation_prompt,
    build_revision_planning_prompt,
    build_template_selection_prompt,
)
from .schema import (
    AgentResponse,
    RetrievalResult,
    RevisionPlan,
    SessionState,
    SessionStatus,
    TemplateSelectionResult,
    TemplateShortInfo,
)
from .state import SessionStateManager


logger = logging.getLogger(__name__)
MODEL_EMPTY_RESPONSE_RETRIES = 3


def _preview(text: object, limit: int = 300) -> str:
    raw = str(text).replace("\n", "\\n")
    if len(raw) <= limit:
        return raw
    return raw[:limit] + "...[truncated]"


def _safe_dump_completion(completion: object) -> str:
    try:
        if hasattr(completion, "model_dump_json"):
            return _preview(completion.model_dump_json())
        if hasattr(completion, "model_dump"):
            return _preview(completion.model_dump())
    except Exception:
        pass
    return _preview(completion)




class DocumentAgent:
    def __init__(
        self,
        state_manager: SessionStateManager,
        list_templates_fn: Callable[[], List[TemplateShortInfo]],
        load_template_fn: Callable[[str], dict],
        compile_latex_fn: Callable[[str, str, int], dict],
        rag_search_fn: Optional[Callable[[str], str]] = None,
        web_search_fn: Optional[Callable[[str], str]] = None,
        model_name:  Optional[str] = None,
        site_url: Optional[str] = None,
        site_name: Optional[str] = None,
    ) -> None:
        env_path = Path(__file__).resolve().parent.parent / ".env"
        load_dotenv(dotenv_path=env_path)

        resolved_model_name = (model_name or os.getenv("AGENT_MODEL") or "").strip()
        if not resolved_model_name:
            raise ValueError("Neither model_name nor AGENT_MODEL is set")

        api_key = (os.getenv("API_KEY_OPENROUTER") or os.getenv("OPENROUTER_API_KEY") or "").strip()
        if not api_key:
            raise ValueError("Neither API_KEY_OPENROUTER nor OPENROUTER_API_KEY is set")

        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
        )

        self.model_name = resolved_model_name
        self.site_url = site_url
        self.site_name = site_name

        self.state_manager = state_manager
        self.list_templates_fn = list_templates_fn
        self.load_template_fn = load_template_fn
        self.compile_latex_fn = compile_latex_fn
        self.rag_search_fn = rag_search_fn
        self.web_search_fn = web_search_fn

    def handle_message(self, session_id: str, user_message: str) -> AgentResponse:
        user_message = (user_message or "").strip()
        if not user_message:
            return AgentResponse(
                message="Пустое сообщение пользователя.",
                success=False,
                error="Empty user message.",
            )

        logger.info("Agent received message | session_id=%s | text=%s", session_id, _preview(user_message))
        state = self.state_manager.append_user_message(session_id, user_message)
        processing_steps: List[str] = []

        try:
            if state.is_empty():
                logger.info("Session %s is empty -> starting new document flow", session_id)
                response = self._handle_new_document(
                    state=state,
                    user_message=user_message,
                    processing_steps=processing_steps,
                )
            else:
                logger.info("Session %s has active document -> starting revision flow", session_id)
                response = self._handle_revision(
                    state=state,
                    user_message=user_message,
                    processing_steps=processing_steps,
                )

            self.state_manager.append_agent_message(session_id, response.message)
            response.processing_steps = processing_steps
            logger.info(
                "Agent finished message | session_id=%s | success=%s | pdf_ready=%s | version=%s",
                session_id,
                response.success,
                response.pdf_ready,
                response.version,
            )
            return response

        except Exception as exc:
            error_text = f"Ошибка при обработке сообщения: {exc}"
            self.state_manager.mark_error(session_id, error_text)
            self.state_manager.append_agent_message(session_id, "Не удалось обработать запрос пользователя.")
            logger.exception("Agent failed | session_id=%s | error=%s", session_id, exc)
            return AgentResponse(
                message="Не удалось обработать запрос пользователя.",
                success=False,
                error=error_text,
                processing_steps=processing_steps,
            )

    def reset_session(self, session_id: str) -> AgentResponse:
        self.state_manager.reset(session_id)
        self.state_manager.append_agent_message(session_id, "Контекст сессии успешно сброшен.")
        logger.info("Session reset | session_id=%s", session_id)
        return AgentResponse(
            message="Контекст сессии успешно сброшен.",
            success=True,
            pdf_ready=False,
        )

    def _handle_new_document(
        self,
        state: SessionState,
        user_message: str,
        processing_steps: List[str],
    ) -> AgentResponse:
        self._add_processing_step(state.session_id, processing_steps, "Анализирую запрос и определяю тип документа.")
        templates = self.list_templates_fn()
        if not templates:
            raise RuntimeError("Не найдено ни одного шаблона документа.")

        logger.info("New document flow | session_id=%s | templates_available=%s", state.session_id, len(templates))

        selection = self._run_template_selection(
            user_message=user_message,
            templates=templates,
        )
        logger.info(
            "Template selected | session_id=%s | template_id=%s | use_rag=%s | use_web=%s",
            state.session_id,
            selection.template_id,
            selection.use_rag,
            selection.use_web,
        )

        template_data = self.load_template_fn(selection.template_id)
        template_latex = template_data["latex"]
        template_name = template_data["name"]
        template_description = template_data["description"]
        logger.info(
            "Template loaded | session_id=%s | template_id=%s | name=%s | latex_length=%s",
            state.session_id,
            selection.template_id,
            template_name,
            len(template_latex),
        )
        self._add_processing_step(
            state.session_id,
            processing_steps,
            f"Подобран шаблон документа: {template_name}.",
        )

        if selection.use_rag and selection.rag_queries:
            self._add_processing_step(
                state.session_id,
                processing_steps,
                "Выполняю поиск по корпоративной базе знаний.",
            )

        if selection.use_web and selection.web_queries:
            self._add_processing_step(
                state.session_id,
                processing_steps,
                "Выполняю поиск в интернете по нормативным и справочным источникам.",
            )

        retrieval_results = self._run_retrieval(
            use_rag=selection.use_rag,
            use_web=selection.use_web,
            rag_queries=selection.rag_queries,
            web_queries=selection.web_queries,
        )
        logger.info(
            "Retrieval finished | session_id=%s | results=%s",
            state.session_id,
            len(retrieval_results),
        )

        self._add_processing_step(
            state.session_id,
            processing_steps,
            "Формирую финальный LaTeX-документ по выбранному шаблону.",
        )
        latex_code = self._run_new_document_generation(
            user_message=user_message,
            template_id=selection.template_id,
            template_name=template_name,
            template_description=template_description,
            template_latex=template_latex,
            retrieval_results=retrieval_results,
        )
        logger.info(
            "LaTeX generated | session_id=%s | length=%s | preview=%s",
            state.session_id,
            len(latex_code),
            _preview(latex_code),
        )

        self._add_processing_step(state.session_id, processing_steps, "Компилирую PDF-документ.")
        compile_result = self._compile_pdf(
            latex_code=latex_code,
            session_id=state.session_id,
            version=1,
        )
        logger.info(
            "PDF compiled | session_id=%s | tex_path=%s | pdf_path=%s",
            state.session_id,
            compile_result["tex_path"],
            compile_result["pdf_path"],
        )

        state.original_user_request = user_message
        state.current_template_id = selection.template_id
        state.current_template_name = template_name
        state.current_template_description = template_description
        state.current_template_latex = template_latex
        state.current_latex = latex_code
        state.current_tex_path = compile_result["tex_path"]
        state.current_pdf_path = compile_result["pdf_path"]
        state.retrieval_results = retrieval_results
        state.version = 1
        state.status = SessionStatus.GENERATED
        state.last_error = None

        self.state_manager.save(state)

        return AgentResponse(
            message="Документ успешно сформирован.",
            success=True,
            pdf_ready=True,
            pdf_path=state.current_pdf_path,
            tex_path=state.current_tex_path,
            latex_code=state.current_latex,
            template_id=state.current_template_id,
            version=state.version,
        )

    def _handle_revision(
        self,
        state: SessionState,
        user_message: str,
        processing_steps: List[str],
    ) -> AgentResponse:
        self._add_processing_step(
            state.session_id,
            processing_steps,
            "Анализирую замечания и планирую обновление документа.",
        )
        revision_plan = self._run_revision_planning(
            user_message=user_message,
            state=state,
        )
        logger.info(
            "Revision plan | session_id=%s | needs_rag=%s | needs_web=%s | instruction=%s",
            state.session_id,
            revision_plan.needs_rag,
            revision_plan.needs_web,
            _preview(revision_plan.edit_instruction),
        )

        if revision_plan.needs_rag and revision_plan.rag_queries:
            self._add_processing_step(
                state.session_id,
                processing_steps,
                "Уточняю данные через корпоративную базу знаний.",
            )

        if revision_plan.needs_web and revision_plan.web_queries:
            self._add_processing_step(
                state.session_id,
                processing_steps,
                "Уточняю данные через поиск в интернете.",
            )

        new_retrieval_results = self._run_retrieval(
            use_rag=revision_plan.needs_rag,
            use_web=revision_plan.needs_web,
            rag_queries=revision_plan.rag_queries,
            web_queries=revision_plan.web_queries,
        )
        logger.info(
            "Revision retrieval finished | session_id=%s | new_results=%s",
            state.session_id,
            len(new_retrieval_results),
        )

        self._add_processing_step(
            state.session_id,
            processing_steps,
            "Обновляю содержимое документа с учетом замечаний.",
        )
        updated_latex = self._run_revision_generation(
            user_message=user_message,
            state=state,
            new_retrieval_results=new_retrieval_results,
            edit_instruction=revision_plan.edit_instruction,
        )
        logger.info(
            "Revised LaTeX generated | session_id=%s | length=%s | preview=%s",
            state.session_id,
            len(updated_latex),
            _preview(updated_latex),
        )

        new_version = state.version + 1
        self._add_processing_step(
            state.session_id,
            processing_steps,
            "Компилирую новую версию PDF-документа.",
        )
        compile_result = self._compile_pdf(
            latex_code=updated_latex,
            session_id=state.session_id,
            version=new_version,
        )
        logger.info(
            "Revised PDF compiled | session_id=%s | version=%s | tex_path=%s | pdf_path=%s",
            state.session_id,
            new_version,
            compile_result["tex_path"],
            compile_result["pdf_path"],
        )

        state.current_latex = updated_latex
        state.current_tex_path = compile_result["tex_path"]
        state.current_pdf_path = compile_result["pdf_path"]
        state.retrieval_results.extend(new_retrieval_results)
        state.version = new_version
        state.status = SessionStatus.REVISED
        state.last_error = None

        self.state_manager.save(state)

        return AgentResponse(
            message="Документ успешно обновлен.",
            success=True,
            pdf_ready=True,
            pdf_path=state.current_pdf_path,
            tex_path=state.current_tex_path,
            latex_code=state.current_latex,
            template_id=state.current_template_id,
            version=state.version,
        )

    def _run_template_selection(
        self,
        user_message: str,
        templates: List[TemplateShortInfo],
    ) -> TemplateSelectionResult:
        prompt = build_template_selection_prompt(
            user_message=user_message,
            templates=templates,
        )
        raw_response = self._call_model(prompt)
        data = self._parse_json_response(raw_response)
        logger.info("Template selection raw response | %s", _preview(raw_response))

        return TemplateSelectionResult(
            template_id=data["template_id"],
            use_rag=bool(data.get("use_rag", False)),
            use_web=bool(data.get("use_web", False)),
            rag_queries=self._ensure_str_list(data.get("rag_queries", [])),
            web_queries=self._ensure_str_list(data.get("web_queries", [])),
            reasoning=data.get("reasoning"),
        )

    def _run_revision_planning(
        self,
        user_message: str,
        state: SessionState,
    ) -> RevisionPlan:
        prompt = build_revision_planning_prompt(
            user_message=user_message,
            state=state,
        )
        raw_response = self._call_model(prompt)
        data = self._parse_json_response(raw_response)
        logger.info("Revision planning raw response | %s", _preview(raw_response))

        return RevisionPlan(
            needs_rag=bool(data.get("needs_rag", False)),
            needs_web=bool(data.get("needs_web", False)),
            rag_queries=self._ensure_str_list(data.get("rag_queries", [])),
            web_queries=self._ensure_str_list(data.get("web_queries", [])),
            edit_instruction=data.get("edit_instruction"),
            reasoning=data.get("reasoning"),
        )

    def _run_retrieval(
        self,
        use_rag: bool,
        use_web: bool,
        rag_queries: List[str],
        web_queries: List[str],
    ) -> List[RetrievalResult]:
        results: List[RetrievalResult] = []

        if use_rag and rag_queries:
            if self.rag_search_fn is None:
                raise RuntimeError("RAG tool is requested but rag_search_fn is not configured.")

            for query in rag_queries:
                logger.info("Calling RAG tool | query=%s", _preview(query))
                content = self.rag_search_fn(query)
                logger.info("RAG tool result | query=%s | content=%s", _preview(query), _preview(content))
                results.append(
                    RetrievalResult(
                        source="rag",
                        query=query,
                        content=content,
                    )
                )

        if use_web and web_queries:
            if self.web_search_fn is None:
                raise RuntimeError("Web search tool is requested but web_search_fn is not configured.")

            for query in web_queries:
                logger.info("Calling web search tool | query=%s", _preview(query))
                content = self.web_search_fn(query)
                logger.info("Web search result | query=%s | content=%s", _preview(query), _preview(content))
                results.append(
                    RetrievalResult(
                        source="web",
                        query=query,
                        content=content,
                    )
                )

        return results

    def _run_new_document_generation(
        self,
        user_message: str,
        template_id: str,
        template_name: str,
        template_description: str,
        template_latex: str,
        retrieval_results: List[RetrievalResult],
    ) -> str:
        prompt = build_new_document_generation_prompt(
            user_message=user_message,
            template_id=template_id,
            template_name=template_name,
            template_description=template_description,
            template_latex=template_latex,
            retrieval_results=retrieval_results,
        )
        return self._call_model(prompt).strip()

    def _run_revision_generation(
        self,
        user_message: str,
        state: SessionState,
        new_retrieval_results: Optional[List[RetrievalResult]] = None,
        edit_instruction: Optional[str] = None,
    ) -> str:
        prompt = build_revision_generation_prompt(
            user_message=user_message,
            state=state,
            new_retrieval_results=new_retrieval_results,
            edit_instruction=edit_instruction,
        )
        return self._call_model(prompt).strip()

    def _compile_pdf(self, latex_code: str, session_id: str, version: int) -> dict:
        compile_result = self.compile_latex_fn(
            latex_code,
            session_id,
            version,
        )

        if not isinstance(compile_result, dict):
            raise RuntimeError("compile_latex_fn must return dict with tex_path and pdf_path.")

        tex_path = compile_result.get("tex_path")
        pdf_path = compile_result.get("pdf_path")

        if not tex_path or not pdf_path:
            raise RuntimeError("Compilation result must contain tex_path and pdf_path.")

        return compile_result

    def _add_processing_step(self, session_id: str, steps: List[str], text: str) -> None:
        cleaned = (text or "").strip()
        if not cleaned:
            return
        if not steps or steps[-1] != cleaned:
            steps.append(cleaned)
            self.state_manager.upsert_processing_message(session_id, "\n".join(steps))

    def _call_model(self, prompt: str) -> str:
        extra_headers = {}
        if self.site_url:
            extra_headers["HTTP-Referer"] = self.site_url
        if self.site_name:
            extra_headers["X-OpenRouter-Title"] = self.site_name

        logger.info(
            "Calling model | model=%s | prompt_length=%s | prompt_preview=%s",
            self.model_name,
            len(prompt),
            _preview(prompt),
        )

        last_error: Exception | None = None

        for attempt in range(1, MODEL_EMPTY_RESPONSE_RETRIES + 1):
            completion = self.client.chat.completions.create(
                extra_headers=extra_headers,
                extra_body={},
                model=self.model_name,
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
            )

            choices = getattr(completion, "choices", None) or []
            if not choices:
                logger.warning(
                    "Model returned no choices | model=%s | attempt=%s/%s | completion=%s",
                    self.model_name,
                    attempt,
                    MODEL_EMPTY_RESPONSE_RETRIES,
                    _safe_dump_completion(completion),
                )
                last_error = RuntimeError("Model returned no choices.")
                if attempt < MODEL_EMPTY_RESPONSE_RETRIES:
                    time.sleep(1.0 * attempt)
                    continue
                raise last_error

            first_choice = choices[0]
            message = getattr(first_choice, "message", None)
            if message is None:
                logger.warning(
                    "Model returned choice without message | model=%s | attempt=%s/%s | completion=%s",
                    self.model_name,
                    attempt,
                    MODEL_EMPTY_RESPONSE_RETRIES,
                    _safe_dump_completion(completion),
                )
                last_error = RuntimeError("Model returned choice without message.")
                if attempt < MODEL_EMPTY_RESPONSE_RETRIES:
                    time.sleep(1.0 * attempt)
                    continue
                raise last_error

            content = getattr(message, "content", "")
            if isinstance(content, list):
                parts = []
                for item in content:
                    if isinstance(item, dict):
                        text = item.get("text")
                        if text:
                            parts.append(text)
                    else:
                        text = getattr(item, "text", None)
                        if text:
                            parts.append(text)
                content = "\n".join(parts)

            if not content or not isinstance(content, str):
                logger.warning(
                    "Model returned empty response | model=%s | attempt=%s/%s | completion=%s",
                    self.model_name,
                    attempt,
                    MODEL_EMPTY_RESPONSE_RETRIES,
                    _safe_dump_completion(completion),
                )
                last_error = RuntimeError("Model returned empty response.")
                if attempt < MODEL_EMPTY_RESPONSE_RETRIES:
                    time.sleep(1.0 * attempt)
                    continue
                raise last_error

            logger.info("Model response received | model=%s | response=%s", self.model_name, _preview(content))
            return content.strip()

        raise last_error or RuntimeError("Model call failed.")

    @staticmethod
    def _parse_json_response(raw_text: str) -> dict:
        cleaned = raw_text.strip()

        if cleaned.startswith("```"):
            cleaned = cleaned.removeprefix("```json").removeprefix("```").strip()
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3].strip()

        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError(f"Failed to parse JSON response from model: {raw_text}")

        json_text = cleaned[start : end + 1]
        return json.loads(json_text)

    @staticmethod
    def _ensure_str_list(value: object) -> List[str]:
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
