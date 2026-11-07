#!/usr/bin/env bash
# Bring the `data` branch (state, history, archive) into newsroom/state.
# The branch is created on the first run.
set -euo pipefail
cd "$(dirname "$0")/.."

REMOTE="https://x-access-token:${GH_TOKEN}@github.com/${GITHUB_REPOSITORY}.git"
rm -rf state
if git ls-remote --exit-code --heads "$REMOTE" data >/dev/null 2>&1; then
  git clone --quiet --depth 1 --branch data --single-branch "$REMOTE" state
else
  echo "no data branch yet - starting fresh"
  mkdir -p state
  git -C state init --quiet -b data
  git -C state remote add origin "$REMOTE"
fi
