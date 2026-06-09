#!/usr/bin/env bash

# Shared env loader for local scripts.
# Source this file from other scripts; do not execute directly.

if [[ -f ".env" ]]; then
  set -a
  source ".env"
  set +a
fi
