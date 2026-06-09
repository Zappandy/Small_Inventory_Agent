#!/usr/bin/env bash
set -euo pipefail

source scripts/_env.sh

rm -f data/dukaan.db
uv run python smoke_tests/smoke_test.py
uv run python -m unittest discover -s smoke_tests -p 'test_*.py'
