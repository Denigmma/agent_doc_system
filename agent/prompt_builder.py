from __future__ import annotations

import json
from typing import List, Optional

from .schema import RetrievalResult, SessionState, TemplateShortInfo


def _templates_to_json(templates: List[TemplateShortInfo]) -> str:
    payload = [
        {
            "template_id": item.template_id,
            "name": item.name,
            "description": item.description,
            "keywords": item.keywords,
        }
        for item in templates
    ]
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _retrievals_to_json(retrieval_results: List[RetrievalResult]) -> str:
    payload = [
        {
            "source": item.source,
            "query": item.query,
            "content": item.content,
        }
        for item in retrieval_results
    ]
    return json.dumps(payload, ensure_ascii=False, indent=2)


def build_template_selection_prompt(
    user_message: str,
    templates: List[TemplateShortInfo],
) -> str:
    templates_json = _templates_to_json(templates)

    return rf"""
Ты — агент-оркестратор системы подготовки технической документации и отчетности.

Твоя задача:
1. Проанализировать запрос пользователя.
2. Выбрать ОДИН наиболее подходящий шаблон документа из списка.
3. Определить, нужен ли поиск по корпоративной базе знаний (RAG).
4. Определить, нужен ли веб-поиск.
5. Сформулировать поисковые запросы для RAG и веб-поиска, если они нужны.

Запрос пользователя:
\"\"\"
{user_message}
\"\"\"

Доступные шаблоны:
{templates_json}

Правила:
- Выбирай только один template_id.
- Если пользователь просит создать документ на основе регламентов, норм, ГОСТов, инструкций, технических требований или внутренних документов, то use_rag=true.
- Если для ответа могут понадобиться внешние нормативные данные, общедоступные стандарты или внешняя справочная информация, то use_web=true.
- Если веб-поиск не нужен, web_queries должен быть пустым массивом.
- Если RAG не нужен, rag_queries должен быть пустым массивом.
- Формулируй запросы кратко, точно и предметно.
- Не придумывай несуществующие шаблоны.
- Ответ верни строго в JSON без пояснений и markdown.

Формат ответа:
{{
  "template_id": "string",
  "use_rag": true,
  "use_web": false,
  "rag_queries": ["query1", "query2"],
  "web_queries": [],
  "reasoning": "краткое объяснение выбора"
}}
""".strip()


def build_new_document_generation_prompt(
    user_message: str,
    template_id: str,
    template_name: str,
    template_description: str,
    template_latex: str,
    retrieval_results: List[RetrievalResult],
) -> str:
    retrieval_json = _retrievals_to_json(retrieval_results)

    return rf"""
Ты — интеллектуальный агент, который формирует готовый LaTeX-документ на основе шаблона и найденного контекста.

Твоя задача:
- взять исходный LaTeX-шаблон,
- заполнить его содержанием,
- сохранить структуру шаблона,
- подставить осмысленный и формальный текст,
- использовать найденную информацию из корпоративной базы знаний и веб-поиска только там, где это уместно,
- не ломать LaTeX-синтаксис.
- НЕ изменять преамбулу шаблона.

Исходный запрос пользователя:
\"\"\"
{user_message}
\"\"\"

Выбранный шаблон:
- template_id: {template_id}
- template_name: {template_name}
- template_description: {template_description}

Исходный LaTeX шаблон:
\"\"\"
{template_latex}
\"\"\"

Найденный контекст:
{retrieval_json}

Требования к результату:
1. Верни ПОЛНЫЙ готовый LaTeX код документа целиком.
2. Не добавляй пояснений, комментариев, markdown-обрамления или ```latex.
3. Сохрани официальный, деловой, технический стиль.
4. Если каких-то данных не хватает, аккуратно сформулируй нейтральный заполнитель по смыслу, не ломая документ.
5. Если в контексте есть ссылки на регламенты, нормы, инструкции, ГОСТы — используй их в тексте документа уместно и аккуратно.
6. Сохрани преамбулу шаблона БЕЗ ИЗМЕНЕНИЙ: не меняй строки до \begin{{document}}, не добавляй и не удаляй \documentclass, \usepackage, настройки шрифтов, языков, геометрии страницы и служебные команды.
7. Если шаблон уже содержит преамбулу и каркас документа, меняй только содержательную часть документа внутри этого каркаса.
8. Не пиши ничего вне LaTeX-кода.
""".strip()


def build_revision_planning_prompt(
    user_message: str,
    state: SessionState,
) -> str:
    retrieval_json = _retrievals_to_json(state.retrieval_results)

    return rf"""
Ты — агент-оркестратор, который редактирует ранее созданный технический документ.

Твоя задача:
1. Проанализировать замечание пользователя.
2. Понять, можно ли внести правку только на основе текущего контекста.
3. Определить, нужен ли новый поиск по корпоративной базе знаний (RAG).
4. Определить, нужен ли новый веб-поиск.
5. Если поиск нужен — сформулировать поисковые запросы.
6. Сформулировать краткую edit_instruction, что именно нужно изменить в документе.

Текущий запрос пользователя на правку:
\"\"\"
{user_message}
\"\"\"

Исходный запрос пользователя:
\"\"\"
{state.original_user_request or ""}
\"\"\"

Текущий шаблон:
- template_id: {state.current_template_id or ""}
- template_name: {state.current_template_name or ""}
- template_description: {state.current_template_description or ""}

Текущий LaTeX документа:
\"\"\"
{state.current_latex or ""}
\"\"\"

Ранее найденный контекст:
{retrieval_json}

Правила:
- Если правка касается только формулировки, даты, имени, локального абзаца или косметического исправления, обычно новый поиск не нужен.
- Если пользователь просит добавить нормативное обоснование, уточнить технические показатели, изменить ссылку на регламент или проверить внешние данные, поиск может понадобиться.
- Ответ верни строго в JSON без пояснений и markdown.

Формат ответа:
{{
  "needs_rag": false,
  "needs_web": false,
  "rag_queries": [],
  "web_queries": [],
  "edit_instruction": "что именно нужно изменить",
  "reasoning": "краткое объяснение"
}}
""".strip()


def build_revision_generation_prompt(
    user_message: str,
    state: SessionState,
    new_retrieval_results: Optional[List[RetrievalResult]] = None,
    edit_instruction: Optional[str] = None,
) -> str:
    combined_retrievals = list(state.retrieval_results)
    if new_retrieval_results:
        combined_retrievals.extend(new_retrieval_results)

    retrieval_json = _retrievals_to_json(combined_retrievals)

    return rf"""
Ты — интеллектуальный агент, который обновляет ранее созданный LaTeX-документ по замечанию пользователя.

Твоя задача:
- взять текущий LaTeX документа,
- внести в него необходимые изменения,
- при необходимости использовать новый найденный контекст,
- вернуть обновленный LaTeX целиком,
- не ломать структуру и синтаксис LaTeX.
- НЕ менять преамбулу и пакетную часть документа.

Исходный запрос на создание документа:
\"\"\"
{state.original_user_request or ""}
\"\"\"

Новое замечание пользователя:
\"\"\"
{user_message}
\"\"\"

Инструкция на изменение:
\"\"\"
{edit_instruction or ""}
\"\"\"

Шаблон:
- template_id: {state.current_template_id or ""}
- template_name: {state.current_template_name or ""}
- template_description: {state.current_template_description or ""}

Текущий LaTeX документа:
\"\"\"
{state.current_latex or ""}
\"\"\"

Полный доступный контекст:
{retrieval_json}

Требования:
1. Верни ПОЛНЫЙ обновленный LaTeX код документа целиком.
2. Не добавляй пояснений, комментариев, markdown-обрамления или ```latex.
3. Измени только то, что требуется по смыслу замечания пользователя.
4. Сохрани официальный стиль документа.
5. Если есть новые нормативные или технические сведения, аккуратно встрои их в документ.
6. Сохрани преамбулу документа БЕЗ ИЗМЕНЕНИЙ: не меняй строки до \begin{{document}}, не добавляй и не удаляй \documentclass, \usepackage, настройки шрифтов, языков, геометрии страницы и служебные команды.
7. Меняй только содержимое документа после \begin{{document}}, если иное не требуется самим шаблоном.
8. Не пиши ничего вне LaTeX-кода.
""".strip()
