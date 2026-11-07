#!/usr/bin/env bash
# Save newsroom/state back to the `data` branch as a single commit (force-push).
# Keeping only one commit means the branch never grows with history; old archive
# files are pruned by the code itself (archive_days in settings.yaml).
set -euo pipefail
cd "$(dirname "$0")/../state"

[ -d .git ] || { echo "no state repo - nothing to save"; exit 0; }
git config user.name "newsroom-bot"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git checkout --quiet --orphan snapshot
git add -A
git commit --quiet -m "state snapshot $(date -u +%Y-%m-%dT%H:%MZ)" || { echo "empty state"; exit 0; }
for i in 1 2 3; do
  if git push --quiet --force origin snapshot:data; then exit 0; fi
  sleep $((i * 4))
done
echo "could not push state" >&2
exit 1
