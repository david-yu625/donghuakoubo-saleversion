#!/usr/bin/env python3
"""Stable step 01 command entry point."""

from __future__ import annotations

from .prepare import copywriting as _implementation
from .prepare.copywriting import *


OpenAI = _implementation.OpenAI
OpenAIError = _implementation.OpenAIError


def parse_copywriting_payload(text: str):
    return _implementation.parse_copywriting_payload(text)


def generate_copywriting(*args, **kwargs):
    # Keep monkey-patching the legacy entry module working for callers/tests.
    _implementation.OpenAI = OpenAI
    return _implementation.generate_copywriting(*args, **kwargs)


def revise_copywriting(*args, **kwargs):
    # Keep monkey-patching the legacy entry module working for callers/tests.
    _implementation.OpenAI = OpenAI
    return _implementation.revise_copywriting(*args, **kwargs)


def main() -> int:
    _implementation.OpenAI = OpenAI
    return _implementation.main()


if __name__ == "__main__":
    raise SystemExit(main())
