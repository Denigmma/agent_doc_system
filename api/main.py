from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from agent.orchestrator import DocumentAgent
from agent.state import SessionStateManager
from api.routes import ChatRegistry, build_router
from tools.latex_tool import compile_latex, init_latex_tool
from tools.rag_tool import search_rag
from tools.template_tool import init_template_repository, list_templates, load_template
from tools.web_search_tool import search_web


BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DB_DIR = BASE_DIR / "templates_db"
WEBUI_DIR = BASE_DIR / "webui"
STATIC_DIR = WEBUI_DIR / "static"
HTML_TEMPLATES_DIR = WEBUI_DIR / "templates"

SITE_URL = "http://localhost:8000"
SITE_NAME = "Agent Doc System"
LOG_LEVEL = os.getenv("APP_LOG_LEVEL", "INFO").upper()


def configure_logging() -> None:
    root_logger = logging.getLogger()
    if not root_logger.handlers:
        logging.basicConfig(
            level=getattr(logging, LOG_LEVEL, logging.INFO),
            format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        )
    else:
        root_logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(title="Agent Doc System")

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    templates = Jinja2Templates(directory=str(HTML_TEMPLATES_DIR))

    init_template_repository(TEMPLATES_DB_DIR)
    init_latex_tool(
        output_dir=BASE_DIR / "storage" / "generated",
        temp_dir=BASE_DIR / "storage" / "temp",
        tectonic_binary="tectonic",
    )

    state_manager = SessionStateManager()
    chat_registry = ChatRegistry()

    agent = DocumentAgent(
        state_manager=state_manager,
        list_templates_fn=list_templates,
        load_template_fn=load_template,
        compile_latex_fn=compile_latex,
        rag_search_fn=search_rag,
        web_search_fn=search_web,
        model_name=os.getenv("AGENT_MODEL", "openai/gpt-5-nano"),
        site_url=SITE_URL,
        site_name=SITE_NAME,
    )

    @app.get("/")
    def chat_page(request: Request):
        return templates.TemplateResponse(
            request,
            "chat.html",
            {
                "page_title": "Agent Doc System",
            },
        )

    app.include_router(
        build_router(
            agent=agent,
            state_manager=state_manager,
            chat_registry=chat_registry,
        )
    )

    return app


app = create_app()
