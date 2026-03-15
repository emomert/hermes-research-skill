#!/usr/bin/env bash
set -euo pipefail

RUN_DIR="${1:-}"
REPO_NAME="${2:-}"
OWNER="${3:-emomert}"

if [[ -z "$RUN_DIR" || -z "$REPO_NAME" ]]; then
  echo "usage: push_github_repo.sh <run_dir> <repo_name> [owner]" >&2
  exit 2
fi

if ! command -v gh >/dev/null 2>&1; then
  echo "gh CLI is required" >&2
  exit 3
fi

if [[ ! -d "$RUN_DIR" ]]; then
  echo "run directory not found: $RUN_DIR" >&2
  exit 4
fi

cd "$RUN_DIR"

if ! gh auth status >/dev/null 2>&1; then
  echo "gh auth is not ready; run 'gh auth login' first" >&2
  exit 5
fi

if [[ ! -d .git ]]; then
  git init -b main >/dev/null 2>&1
fi

if [[ -z "$(git config user.name || true)" ]]; then
  git config user.name "Hermes Agent"
fi
if [[ -z "$(git config user.email || true)" ]]; then
  git config user.email "hermes-agent@local"
fi

files=(article.tex article.pdf references.bib research_brief.md review_summary.md README.md run_evaluation.md request.json)
staged_any=0
for f in "${files[@]}"; do
  if [[ -f "$f" ]]; then
    git add "$f"
    staged_any=1
  fi
done
if [[ "$staged_any" -eq 0 ]] || git diff --cached --quiet; then
  echo "No changes staged for GitHub push" >&2
else
  git commit -m "Add research article artifacts" >/dev/null 2>&1 || true
fi

if ! gh repo view "$OWNER/$REPO_NAME" >/dev/null 2>&1; then
  gh repo create "$OWNER/$REPO_NAME" --public >/dev/null
fi

REMOTE_URL="https://github.com/${OWNER}/${REPO_NAME}.git"
if git remote get-url origin >/dev/null 2>&1; then
  git remote set-url origin "$REMOTE_URL"
else
  git remote add origin "$REMOTE_URL"
fi

git push -u origin main --force >/dev/null 2>&1

echo "https://github.com/${OWNER}/${REPO_NAME}"
