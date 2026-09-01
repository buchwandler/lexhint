from __future__ import annotations

import unicodedata


def normalize_ipa_body(value: str) -> str:
    """Return an NFC IPA body without one conventional outer delimiter pair."""
    normalized = unicodedata.normalize("NFC", value).strip()
    if len(normalized) >= 2 and (
        (normalized.startswith("/") and normalized.endswith("/"))
        or (normalized.startswith("[") and normalized.endswith("]"))
    ):
        normalized = normalized[1:-1].strip()
    return normalized


def format_ipa(value: str) -> str:
    """Render one IPA transcription in Lexhint's focused human-output style."""
    body = normalize_ipa_body(value)
    return f"[{body}]" if body else ""
