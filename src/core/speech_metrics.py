"""Shared speech-length metrics used by copywriting and the desktop UI."""

from __future__ import annotations

import re


# Punctuation and whitespace affect pauses, but are not counted as "字数".
COUNTABLE_SPEECH_CHAR_RE = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]")

# Calibrated against the project's current Doubao voice profile and generated WAVs.
DEFAULT_SPEECH_CHARS_PER_SECOND = 6.0
SPEECH_ESTIMATE_VARIATION = 0.10


def count_speech_chars(text: str) -> int:
    """Count Chinese, Latin, and numeric characters that are read aloud."""

    return len(COUNTABLE_SPEECH_CHAR_RE.findall(text))


def estimate_speech_duration_seconds(
    char_count: int,
    *,
    chars_per_second: float = DEFAULT_SPEECH_CHARS_PER_SECOND,
) -> float:
    """Estimate narration duration from the number of countable speech chars."""

    if char_count <= 0:
        return 0.0
    if chars_per_second <= 0:
        raise ValueError("chars_per_second 必须大于 0")
    return char_count / chars_per_second


def estimate_speech_duration_range(
    char_count: int,
    *,
    chars_per_second: float = DEFAULT_SPEECH_CHARS_PER_SECOND,
) -> tuple[float, float]:
    """Return a practical duration range accounting for punctuation and pauses."""

    estimate = estimate_speech_duration_seconds(
        char_count,
        chars_per_second=chars_per_second,
    )
    return (
        estimate * (1.0 - SPEECH_ESTIMATE_VARIATION),
        estimate * (1.0 + SPEECH_ESTIMATE_VARIATION),
    )
