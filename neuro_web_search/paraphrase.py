from .models import llm
import re
import enum
from typing import Iterable, Optional


class ParaphaseMode(enum.Enum):
    """
    Enum for paraphrase modes.

    - EXPAND: Expands the query with 5 focus queries.
    - SIMPLIFY: Simplifies the query by generating 1 paraphrase.
    """
    EXPAND = 1
    SIMPLIFY = 0


def paraphrase_query(
    query: str,
    mode: ParaphaseMode = ParaphaseMode.SIMPLIFY,
    history: Optional[Iterable[str]] = None,
) -> list[str]:
    """
    Функция для перефразировки поискового запроса с использованием LLM.
    Возвращает несколько вариантов перефразированного запроса.

    :param query: Исходный поисковый запрос
    :param mode: Режим перефразировки (EXPAND или SIMPLIFY)

    :return: Строка с перефразированными запросами
    :raises AssertionError: Если входные данные не соответствуют ожиданиям
    """

    assert isinstance(query, str), "Query must be a string"
    assert isinstance(mode, ParaphaseMode), "mode must be an instance of ParaphaseMode"

    if mode == ParaphaseMode.EXPAND:
        examples = [
            {
                "input": "как изучать python",
                "output": """
1. Как изучать Python для анализа данных  
2. Как изучать Python с нуля для начинающих  
3. Лучшие ресурсы для изучения Python онлайн  
4. Как изучать Python для веб-разработки  
5. С чего начать изучение Python для автоматизации задач"""
            },
            {
                "input": "apple",
                "output": """
1. История компании Apple  
2. Преимущества iPhone по сравнению с Android  
3. Полезные свойства яблок для здоровья  
4. Текущая стоимость акций компании Apple  
5. Как вырастить яблоню на даче"""
            },
            {
                "input": "машинное обучение",
                "output": """
1. Что такое машинное обучение
2. Основные алгоритмы машинного обучения
3. Курсы и ресурсы по машинному обучению  
4. Роль машинного обучения в искусственном интеллекте  
5. История развития машинного обучения"""
            },
            {
                "input": "Brent crude price today",
                "output": """
1. Brent crude price today live
2. Brent crude oil price per barrel today
3. Current Brent crude price in USD
4. Brent spot price today
5. Brent crude latest market price"""
            },
        ]

        system_prompt = """
Ты — помощник по перефразированию запросов для эффективного поиска информации в интернете, который получает общий пользовательский запрос и генерирует 5 уточняющих версий запроса, каждый из которых фокусируется на отдельном аспекте или подтеме исходного вопроса. 

Требования:
- Сохраняй исходный смысл запроса.
- Сохраняй язык исходного запроса. Если запрос написан на английском языке, не переводи его на русский.
- Запросы должны сохранять смысл, но освещать разные возможные направления уточнения.
- При коротких или неясных запросах — обязательно дополни их для лучшего понимания сути.
- Следи, чтобы дополнения не искажали исходный смысл.
- Стиль формулировок должен оставаться естественным и подходящим для поиска в интернете.
Формат:
- Пронумерованный список.
- Каждый вариант — отдельной строкой.
"""
    elif mode == ParaphaseMode.SIMPLIFY:
        examples = [
            {
                "input": "где найти книги по python",
                "output": "1. Лучшие сайты для скачивания книг по Python"
            },
            {
                "input": "Как приготовить борщ",
                "output": "1. Рецепт борща с пошаговыми инструкциями"
            },
            {
                "input": "Почему не работает интернет",
                "output": "1. Причины, по которым может не работать интернет"
            },
            {
                "input": "Brent crude price today",
                "output": "1. Brent crude price today live per barrel"
            }
        ]

        system_prompt = """
Ты — помощник по перефразированию запросов для эффективного поиска информации в интернете. На основе запроса пользователя сгенерируй 1 перефразировку.

Требования:
- Сохраняй исходный смысл запроса.
- Сохраняй язык исходного запроса. Если запрос написан на английском языке, не переводи его на русский.
- Напиши только 1 вариант перефразировки.
- При коротких или неясных запросах — обязательно дополни их для лучшего понимания сути.
- Следи, чтобы дополнения не искажали исходный смысл.
- Стиль формулировок должен оставаться естественным и подходящим для поиска в интернете.

Формат:
- Пронумерованный список.
- Каждый вариант — отдельной строкой.
- Перефразировка должна быть в формате: "1. [перефразированный запрос]"
"""
    else:
        raise ValueError(f"Unsupported paraphrase mode: {mode}")

    messages = [{"role": "system", "content": system_prompt}]

    for example in examples:
        messages.append({"role": "user", "content": example["input"]})
        messages.append({"role": "assistant", "content": example["output"]})

    history_lines = []
    if history:
        history_lines = [str(item).strip() for item in history if str(item).strip()]

    user_payload = query
    if history_lines:
        user_payload = (
            "История диалога:\n"
            + "\n".join(history_lines[-6:])
            + "\n\nТекущий запрос:\n"
            + query
        )

    messages.append({"role": "user", "content": user_payload})

    try:
        response = llm.invoke(messages)
    except Exception:
        return [query.strip()]

    if not response.strip():
        return [query.strip()]

    paraphrases = list(response.split('\n'))
    paraphrases = [p for p in paraphrases if len(p) > 0 and p[0].isdigit()]
    paraphrases = [re.sub(r'^\s*\d+[\.\-\)]\s*', '', p) for p in paraphrases]

    final_queries: list[str] = []
    original_query = query.strip()
    if original_query:
        final_queries.append(original_query)

    for paraphrase in paraphrases:
        cleaned = paraphrase.strip()
        if not cleaned:
            continue
        if cleaned.lower() == original_query.lower():
            continue
        final_queries.append(cleaned)

    if not final_queries:
        return [original_query]

    return final_queries


if __name__ == "__main__":
    query = "Как изучить тайм-менеджмент"
    paraphrased_queries = paraphrase_query(query, mode=ParaphaseMode.SIMPLIFY)
    print("Paraphrased Queries:")
    for pq in paraphrased_queries:
        print(pq)
