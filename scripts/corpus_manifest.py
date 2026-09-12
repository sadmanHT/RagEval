#!/usr/bin/env python3
"""Convenience wrapper for `python -m rageval.corpus.cli`."""

from rageval.corpus.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
