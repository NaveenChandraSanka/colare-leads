#!/bin/bash
# Colare Lead Scout — run script
# Usage: ./run.sh [--dry-run | --markdown | --schedule | --min-grade B]

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
elif [ -d "../linkedin-digest/venv" ]; then
    # Reuse the existing venv from linkedin-digest (same deps)
    source ../linkedin-digest/venv/bin/activate
fi

# Load .env if present
if [ -f ".env" ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Validate Notion token
if [ -z "$NOTION_TOKEN" ]; then
    echo "⚠️  NOTION_TOKEN not set. Will save to local markdown only."
    echo "   Set it in .env or export NOTION_TOKEN=your_token"
fi

echo "🔍 Starting Colare Lead Scout..."
echo ""

python main.py "$@"
