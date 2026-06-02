#!/usr/bin/env bash
set -euo pipefail

REPO_OWNER="${AI_WIZARD_REPO_OWNER:-thevibethinker}"
REPO_NAME="${AI_WIZARD_REPO_NAME:-ai-wizard-skill}"
BRANCH="${AI_WIZARD_BRANCH:-main}"
SKILL_SLUG="${AI_WIZARD_SKILL_SLUG:-ai-wizard}"
WORKSPACE="${AI_WIZARD_WORKSPACE:-/home/workspace}"
DEST_DIR="${WORKSPACE}/Skills/${SKILL_SLUG}"

if ! command -v curl >/dev/null 2>&1; then
  echo "AI Wizard installer needs curl."
  exit 1
fi

if ! command -v tar >/dev/null 2>&1; then
  echo "AI Wizard installer needs tar."
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "AI Wizard installer needs python3."
  exit 1
fi

if [ ! -d "$WORKSPACE" ]; then
  echo "Workspace not found at $WORKSPACE."
  echo "Run this on your Zo Computer, or set AI_WIZARD_WORKSPACE=/path/to/workspace."
  exit 1
fi

tmpdir="$(mktemp -d)"
cleanup() {
  rm -rf "$tmpdir"
}
trap cleanup EXIT

tarball_url="https://github.com/${REPO_OWNER}/${REPO_NAME}/archive/refs/heads/${BRANCH}.tar.gz"
archive_root="${REPO_NAME}-${BRANCH}"

echo "Installing AI Wizard into ${DEST_DIR}"
mkdir -p "${WORKSPACE}/Skills"
curl -fsSL "$tarball_url" | tar -xz -C "$tmpdir" "${archive_root}/${SKILL_SLUG}"
rm -rf "$DEST_DIR"
mkdir -p "$DEST_DIR"
cp -R "${tmpdir}/${archive_root}/${SKILL_SLUG}/." "$DEST_DIR/"

echo
echo "AI Wizard installed."
echo
python3 "${DEST_DIR}/scripts/ai_wizard.py" scan --mode zo-native >/dev/null
echo "Smoke check passed."
echo
echo "Run your profile:"
echo "  python3 Skills/ai-wizard/scripts/ai_wizard.py profile --mode zo-native --depth capped"
echo
echo "Fast local-only mode:"
echo "  python3 Skills/ai-wizard/scripts/ai_wizard.py profile --mode zo-native --no-semantic"
echo
echo "AI Wizard is local-first. Default public outputs redact raw private evidence."
