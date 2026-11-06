#!/bin/zsh
set -eu
cd "${0:A:h}"
umask 077
if ! command -v uv >/dev/null; then
  print 'The uv installer is missing. Ask the assistant to help install uv.'
  exit 1
fi
uv sync --locked
uv run --locked beli-tool run "$@"
