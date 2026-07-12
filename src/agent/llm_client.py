"""
src/agent/llm_client.py

OpenRouter LLM client wrapper.
- Uses openai-compatible client pointed at OpenRouter endpoint.
- Enforces per-call timeout (NODE_TIMEOUT_SECONDS from config).
- Retries once on failure, feeding validation errors back as correction context.
- All LLM calls return raw text; callers parse with Pydantic.
"""
from __future__ import annotations

import json
import time
from typing import Any, Type

from openai import APIError, APITimeoutError, OpenAI
from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import get_llm_model, get_node_timeout, get_openrouter_api_key, get_openrouter_base_url


def _get_client() -> OpenAI:
    return OpenAI(
        api_key=get_openrouter_api_key(),
        base_url=get_openrouter_base_url(),
        timeout=get_node_timeout(),
    )


class LLMCallError(Exception):
    """Raised when an LLM call fails after retry."""


def call_llm(
    system_prompt: str,
    user_prompt: str,
    response_model: Type[BaseModel] | None = None,
    temperature: float = 0.1,
) -> str | dict[str, Any]:
    """
    Call the LLM with a system + user prompt.

    If response_model is provided, the LLM is asked to respond in JSON
    matching the model's schema; the raw JSON string is returned and the
    caller parses it (so Pydantic validation happens at the call site).

    On failure (timeout or API error), retries once.  After two failures,
    raises LLMCallError — callers map this to PROCESSING_ERROR.
    """
    client = _get_client()
    model = get_llm_model()

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    schema_instruction = ""
    if response_model:
        schema = response_model.model_json_schema()
        schema_instruction = (
            f"\n\nRespond with a single JSON object that exactly matches this schema:\n"
            f"{json.dumps(schema, indent=2)}\n"
            "Do not include any text before or after the JSON object."
        )
        messages[0]["content"] += schema_instruction

    last_error: Exception | None = None
    for attempt in range(2):  # One retry
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=4096,
            )
            content = response.choices[0].message.content or ""
            if response_model:
                # Return raw JSON string — caller validates with Pydantic
                # Strip markdown code fences if present
                content = content.strip()
                if content.startswith("```"):
                    lines = content.split("\n")
                    content = "\n".join(lines[1:-1]) if len(lines) > 2 else content
                return content
            return content

        except (APITimeoutError, APIError) as e:
            last_error = e
            if attempt == 0:
                time.sleep(2)  # Brief pause before retry
            continue

    raise LLMCallError(f"LLM call failed after retry: {last_error}") from last_error


def call_llm_structured(
    system_prompt: str,
    user_prompt: str,
    response_model: Type[BaseModel],
    temperature: float = 0.1,
) -> BaseModel:
    """
    Call LLM and parse the response into a Pydantic model.
    On parse failure, retries once with the validation error fed back as correction.
    Raises LLMCallError after two failures.
    """
    raw = call_llm(system_prompt, user_prompt, response_model, temperature)

    # First parse attempt
    try:
        return response_model.model_validate_json(raw)
    except Exception as first_error:
        pass  # Try once more with correction context

    # Retry with error feedback
    correction_prompt = (
        f"{user_prompt}\n\n"
        f"Your previous response could not be parsed. Validation error:\n{first_error}\n"
        f"Your response was:\n{raw}\n\n"
        "Please correct and return a valid JSON object matching the schema."
    )
    raw2 = call_llm(system_prompt, correction_prompt, response_model, temperature)
    try:
        return response_model.model_validate_json(raw2)
    except Exception as second_error:
        raise LLMCallError(
            f"LLM response failed Pydantic validation after retry.\n"
            f"Final error: {second_error}\nFinal response: {raw2}"
        ) from second_error
