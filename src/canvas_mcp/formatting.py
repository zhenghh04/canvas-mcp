"""Shaping Canvas payloads for a language model: slimming, bounding, redaction.

Canvas objects are wide — a single assignment carries ~50 fields, most of them
URLs and internal flags. Returning them raw burns context and buries the two or
three fields that matter. Every tool therefore projects its result through
:func:`slim` before :func:`format_payload` serialises it.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
from typing import Any

#: Direct identifiers replaced with stable hashes when ``CANVAS_REDACT_PII=1``.
PII_KEYS = frozenset(
    {
        "email",
        "login_id",
        "sis_user_id",
        "sis_login_id",
        "integration_id",
        "primary_email",
        "pseudonym_id",
    }
)

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t]*\n[ \t]*")
_BLOCK_RE = re.compile(r"</(p|div|li|tr|h[1-6]|blockquote)\s*>", re.IGNORECASE)
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)


def pseudonym(value: str) -> str:
    """Stable, non-reversible stand-in for one identifier.

    Stable so a model can still say "the same student appears in both lists";
    hashed so the identifier itself never leaves the machine.
    """
    return "anon-" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:10]


def redact(obj: Any) -> Any:
    """Recursively replace direct identifiers with :func:`pseudonym` hashes."""
    if isinstance(obj, list):
        return [redact(item) for item in obj]
    if isinstance(obj, dict):
        return {
            key: (pseudonym(str(value)) if key in PII_KEYS and value else redact(value))
            for key, value in obj.items()
        }
    return obj


def strip_html(text: str | None) -> str:
    """Render Canvas's rich-text HTML down to readable plain text.

    Block-level close tags become newlines before tags are dropped, so a page
    body does not collapse into one unreadable paragraph.
    """
    if not text:
        return ""
    text = _BR_RE.sub("\n", text)
    text = _BLOCK_RE.sub("\n", text)
    text = _TAG_RE.sub(" ", text)
    text = html.unescape(text)
    text = _WS_RE.sub("\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def slim(item: dict, keys: tuple[str, ...]) -> dict:
    """Project an object down to ``keys``, dropping fields it does not have."""
    return {key: item.get(key) for key in keys if key in item}


def slim_all(items: Any, keys: tuple[str, ...]) -> list[dict]:
    """:func:`slim` every dict in a list, passing non-dicts (truncation markers)
    through untouched so a caller still sees that the result was capped."""
    out: list[dict] = []
    for item in items or []:
        out.append(slim(item, keys) if isinstance(item, dict) else item)
    return out


def format_payload(data: Any, max_chars: int = 0, *, redact_pii: bool = False) -> str:
    """Serialise a payload to the JSON text a tool returns.

    ``max_chars=0`` means unbounded. A truncated payload says so explicitly and
    names the knob, because silent truncation reads to a model as a complete
    answer and it will reason from the missing half.
    """
    if redact_pii:
        data = redact(data)
    text = json.dumps(data, indent=2, default=str, ensure_ascii=False)
    if max_chars and len(text) > max_chars:
        return (
            text[:max_chars] + f"\n... [truncated at {max_chars} of {len(text)} chars; "
            "raise max_chars or narrow the query]"
        )
    return text


def form(**pairs: Any) -> dict[str, Any]:
    """Build Canvas form parameters, dropping anything the caller did not supply.

    "Unset" is ``None`` or ``""``, so a PUT only touches the fields actually
    passed and never blanks a field by omission. ``False`` and ``0`` are real
    values and survive. Booleans render as ``"true"``/``"false"``: Rails
    downcases before comparing, so Python's ``"True"`` would in fact work, but
    the explicit form is what Canvas documents.
    """
    out: dict[str, Any] = {}
    for key, value in pairs.items():
        if value is None or value == "":
            continue
        out[key] = "true" if value is True else "false" if value is False else value
    return out
