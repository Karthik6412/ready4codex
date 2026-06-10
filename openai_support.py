from __future__ import annotations

import json
import os
from typing import Any


OPENAI_MODEL = "gpt-4o-mini"


class OpenAIUnavailable(RuntimeError):
    pass


def openai_enabled() -> bool:
    return bool(os.getenv("OPENAI_API_KEY"))


async def call_openai_json(
    *,
    system_prompt: str,
    payload: dict[str, Any],
    schema_name: str,
    schema: dict[str, Any],
    max_output_tokens: int = 1500,
) -> dict[str, Any]:
    if not openai_enabled():
        raise OpenAIUnavailable("OPENAI_API_KEY is not set.")

    try:
        from openai import AsyncOpenAI
    except ImportError as exc:
        raise OpenAIUnavailable("OpenAI SDK is not installed.") from exc

    client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])
    response = await client.responses.create(
        model=OPENAI_MODEL,
        instructions=system_prompt,
        input=json.dumps(payload, indent=2, sort_keys=True),
        temperature=0,
        max_output_tokens=max_output_tokens,
        timeout=20,
        text={
            "format": {
                "type": "json_schema",
                "name": schema_name,
                "schema": schema,
                "strict": True,
            }
        },
    )

    text = getattr(response, "output_text", "")
    if not text:
        raise OpenAIUnavailable("OpenAI response did not include output text.")

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise OpenAIUnavailable("OpenAI response was not valid JSON.") from exc

    if not isinstance(parsed, dict):
        raise OpenAIUnavailable("OpenAI response JSON was not an object.")
    return parsed


def string_array_schema(keys: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": keys,
        "properties": {
            key: {
                "type": "array",
                "items": {"type": "string"},
            }
            for key in keys
        },
    }
