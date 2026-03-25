from __future__ import annotations

import inspect
import re
from typing import List, Literal, Union

from pydantic import BaseModel, Field


def build_system_prompt(
    instruction: str = "",
    example: str = "",
    pydantic_schema: str = "",
) -> str:
    delimiter = "\n\n---\n\n"
    schema = ""
    if pydantic_schema:
        schema = (
            "Your answer should be in JSON and strictly follow this schema, "
            "filling in the fields in the order they are given:\n"
            "```\n"
            f"{pydantic_schema}\n"
            "```"
        )

    parts = [instruction.strip()]
    if schema:
        parts.append(schema.strip())
    if example:
        parts.append(example.strip())

    return delimiter.join([p for p in parts if p])


ANSWER_SHARED_INSTRUCTION = """
You are a RAG answering system for Gazprom technical and normative documentation.

You will receive:
- a user question
- retrieved context from one or more pages of source PDF documents

The corpus may include:
- technical standards and regulations
- Gazprom internal standards and corporate documents
- ГОСТ, СТО, РД, ТУ, instructions, procedures, safety rules
- equipment-related documentation
- maintenance, acceptance, control, storage, transportation, and operational requirements

Your task is to answer the question using ONLY the provided context.

Core rules:
- Use only facts explicitly supported by the context
- Do not invent missing facts
- Do not rely on outside knowledge
- Do not merge weakly related fragments into a stronger conclusion than the text supports
- If the answer is not clearly supported by the context, return "N/A"

For this domain, be especially careful about:
- exact document references and standard numbers
- exact requirements, restrictions, prohibitions, or mandatory conditions
- exact scope of application
- exact roles, responsibilities, or procedures
- exact technical terms and definitions
- differences between general background text and normative statements

Prefer conservative, document-grounded answers.
If the retrieved pages are related to the topic but do not directly support the asked point, return "N/A".
""".strip()

ANSWER_SHARED_USER_PROMPT = """
Here is the context:
\"\"\"
{context}
\"\"\"

---

Here is the question:
"{question}"
""".strip()


class AnswerWithRAGContextNamePrompt:
    instruction = ANSWER_SHARED_INSTRUCTION
    user_prompt = ANSWER_SHARED_USER_PROMPT

    class AnswerSchema(BaseModel):
        step_by_step_analysis: str = Field(
            description=(
                "Detailed step-by-step analysis of the answer with at least 5 steps and at least 120 words. "
                "Carefully compare the wording of the question with the wording in the context. "
                "Do not confuse similar entities, similar terms, or related concepts."
            )
        )

        reasoning_summary: str = Field(
            description="Concise summary of the reasoning. Around 40-70 words."
        )

        relevant_pages: List[int] = Field(
            description="""
List of page numbers directly used to answer the question.
Include only pages that contain direct evidence or strong support for the answer.
Do not include pages that are only weakly related.
At least one page should be included if a non-N/A answer is given.
"""
        )

        final_answer: Union[str, Literal["N/A"]] = Field(
            description="""
Return a single name or named entity exactly as supported by the context.
Examples:
- person full name
- term
- concept name
- method name
- compound name
- topic name

Do not add explanations or comments.
Return "N/A" if the answer is not clearly available in the context.
"""
        )

    pydantic_schema = re.sub(
        r"^ {4}",
        "",
        inspect.getsource(AnswerSchema),
        flags=re.MULTILINE,
    )
    system_prompt_with_schema = build_system_prompt(
        instruction,
        example="",
        pydantic_schema=pydantic_schema,
    )


class AnswerWithRAGContextNumberPrompt:
    instruction = ANSWER_SHARED_INSTRUCTION
    user_prompt = ANSWER_SHARED_USER_PROMPT

    class AnswerSchema(BaseModel):
        step_by_step_analysis: str = Field(
            description="""
Detailed step-by-step analysis of the answer with at least 5 steps and at least 120 words.

Strict numeric matching rules:
1. Identify exactly what quantity the question asks for.
2. Use only a value directly stated in the context.
3. Accept only if the metric or quantity in the context matches the question exactly.
4. Return "N/A" if:
   - the value would need to be calculated
   - the quantity is only approximate
   - the unit or scale is unclear
   - the context contains only related but not identical numbers
5. Be conservative if there is any ambiguity.
"""
        )

        reasoning_summary: str = Field(
            description="Concise summary of the reasoning. Around 40-70 words."
        )

        relevant_pages: List[int] = Field(
            description="""
List of page numbers directly used to answer the question.
Include only pages that contain direct evidence or strong support for the answer.
Do not include pages that are only weakly related.
At least one page should be included if a non-N/A answer is given.
"""
        )

        final_answer: Union[float, int, Literal["N/A"]] = Field(
            description="""
Return a numeric value only.

Rules:
- Preserve the actual numeric meaning from the context
- Convert decimal commas to decimal points if needed
- Parentheses may indicate negative values
- Respect units, thousands, millions, percentages, etc. only if explicitly stated in the context
- Do not calculate missing values
- Return "N/A" if the number is not directly and clearly supported by the context
"""
        )

    pydantic_schema = re.sub(
        r"^ {4}",
        "",
        inspect.getsource(AnswerSchema),
        flags=re.MULTILINE,
    )
    system_prompt_with_schema = build_system_prompt(
        instruction,
        example="",
        pydantic_schema=pydantic_schema,
    )


class AnswerWithRAGContextBooleanPrompt:
    instruction = ANSWER_SHARED_INSTRUCTION
    user_prompt = ANSWER_SHARED_USER_PROMPT

    class AnswerSchema(BaseModel):
        step_by_step_analysis: str = Field(
            description=(
                "Detailed step-by-step analysis of the answer with at least 5 steps and at least 120 words. "
                "Determine whether the context clearly supports True or clearly supports False. "
                "If the context is insufficient or ambiguous, prefer a conservative interpretation in the reasoning."
            )
        )

        reasoning_summary: str = Field(
            description="Concise summary of the reasoning. Around 40-70 words."
        )

        relevant_pages: List[int] = Field(
            description="""
List of page numbers directly used to answer the question.
Include only pages that contain direct evidence or strong support for the answer.
Do not include pages that are only weakly related.
At least one page should be included.
"""
        )

        final_answer: bool = Field(
            description="""
Return:
- true if the context clearly supports that the statement in the question is correct
- false if the context clearly supports that the statement in the question is incorrect

Do not guess beyond the provided context.
"""
        )

    pydantic_schema = re.sub(
        r"^ {4}",
        "",
        inspect.getsource(AnswerSchema),
        flags=re.MULTILINE,
    )
    system_prompt_with_schema = build_system_prompt(
        instruction,
        example="",
        pydantic_schema=pydantic_schema,
    )


class AnswerWithRAGContextNamesPrompt:
    instruction = ANSWER_SHARED_INSTRUCTION
    user_prompt = ANSWER_SHARED_USER_PROMPT

    class AnswerSchema(BaseModel):
        step_by_step_analysis: str = Field(
            description=(
                "Detailed step-by-step analysis of the answer with at least 5 steps and at least 120 words. "
                "Carefully distinguish between exact requested entities and merely related entities."
            )
        )

        reasoning_summary: str = Field(
            description="Concise summary of the reasoning. Around 40-70 words."
        )

        relevant_pages: List[int] = Field(
            description="""
List of page numbers directly used to answer the question.
Include only pages that contain direct evidence or strong support for the answer.
Do not include pages that are only weakly related.
At least one page should be included if a non-N/A answer is given.
"""
        )

        final_answer: Union[List[str], Literal["N/A"]] = Field(
            description="""
Return a list of exact items supported by the context.

Possible outputs may include:
- names of people
- terms
- concepts
- methods
- compounds
- stages
- categories
- products
- titles

Rules:
- each entry should be concise
- each entry should match the context
- avoid duplicates
- do not add explanations
- return "N/A" if the requested list is not clearly available
"""
        )

    pydantic_schema = re.sub(
        r"^ {4}",
        "",
        inspect.getsource(AnswerSchema),
        flags=re.MULTILINE,
    )
    system_prompt_with_schema = build_system_prompt(
        instruction,
        example="",
        pydantic_schema=pydantic_schema,
    )


class AnswerWithRAGContextTextPrompt:
    instruction = ANSWER_SHARED_INSTRUCTION
    user_prompt = ANSWER_SHARED_USER_PROMPT

    class AnswerSchema(BaseModel):
        step_by_step_analysis: str = Field(
            description=(
                "Detailed step-by-step analysis of the answer with at least 5 steps and at least 120 words. "
                "Identify the most relevant evidence from the context and explain how it supports the answer."
            )
        )

        reasoning_summary: str = Field(
            description="Concise summary of the reasoning. Around 40-70 words."
        )

        relevant_pages: List[int] = Field(
            description="""
List of page numbers directly used to answer the question.
Include only pages that contain direct evidence or strong support for the answer.
Do not include pages that are only weakly related.
At least one page should be included if a non-N/A answer is given.
"""
        )

        final_answer: Union[str, Literal["N/A"]] = Field(
            description="""
Return a concise natural-language answer based only on the context.

Rules:
- answer the question directly
- do not mention that you are using context
- do not mention page numbers
- do not add unsupported facts
- keep the answer informative but concise
- return "N/A" if the answer is not clearly supported by the context
"""
        )

    pydantic_schema = re.sub(
        r"^ {4}",
        "",
        inspect.getsource(AnswerSchema),
        flags=re.MULTILINE,
    )
    system_prompt_with_schema = build_system_prompt(
        instruction,
        example="",
        pydantic_schema=pydantic_schema,
    )


ANSWER_SCHEMA_FIX_SYSTEM_PROMPT = """
You are a JSON formatter.

Your task is to convert a raw LLM response into a valid JSON object.

Rules:
- Output only JSON
- Do not add markdown, comments, or explanations
- The response must start with '{' and end with '}'
- Preserve the intended structure and content as closely as possible
""".strip()

ANSWER_SCHEMA_FIX_USER_PROMPT = """
Here is the system prompt that defines the required JSON schema:
\"\"\"
{system_prompt}
\"\"\"

---

Here is the LLM response that does not follow the schema and needs to be reformatted:
\"\"\"
{response}
\"\"\"
""".strip()