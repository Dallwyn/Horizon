"""Shared AI utility functions."""

import json
import re
from typing import Optional


def unwrap_retry_error(exc: BaseException) -> BaseException:
    """Return the underlying cause of a tenacity RetryError, if any.

    ``str(RetryError(...))`` only prints a Future repr (e.g.
    ``RetryError[<Future ... state=finished raised ClientError>]``), which
    hides the actual provider error message needed to tell a bad API key
    apart from a real rate limit. Retries elsewhere in this project use
    ``tenacity.retry``, so this unwraps duck-typed ``last_attempt`` futures
    rather than importing tenacity just for an isinstance check.
    """
    last_attempt = getattr(exc, "last_attempt", None)
    if last_attempt is not None and hasattr(last_attempt, "exception"):
        try:
            cause = last_attempt.exception()
        except Exception:
            cause = None
        if cause is not None:
            return cause
    return exc


def parse_json_response(response: str) -> Optional[dict]:
    """Try multiple strategies to extract a JSON object from an AI response.

    Returns the parsed dict, or None if all strategies fail.
    """
    text = response.strip()

    # Strategy 1: direct parse
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass

    # Strategy 2: extract from ```json ... ``` code block
    if "```json" in text:
        try:
            json_str = text.split("```json")[1].split("```")[0].strip()
            return json.loads(json_str)
        except (json.JSONDecodeError, ValueError, IndexError):
            pass

    # Strategy 3: extract from ``` ... ``` code block
    if "```" in text:
        try:
            json_str = text.split("```")[1].split("```")[0].strip()
            return json.loads(json_str)
        except (json.JSONDecodeError, ValueError, IndexError):
            pass

    # Strategy 4: find the first { ... } block using brace matching
    start = text.find("{")
    if start != -1:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except (json.JSONDecodeError, ValueError):
                        break

    # Strategy 5: regex extraction as last resort
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            return json.loads(match.group())
        except (json.JSONDecodeError, ValueError):
            pass

    return None
