#!/usr/bin/env python3
"""Standalone cover generation command entry point."""

from __future__ import annotations

from .prepare.cover import main


if __name__ == "__main__":
    raise SystemExit(main())
