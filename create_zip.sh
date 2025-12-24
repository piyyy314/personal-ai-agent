#!/usr/bin/env bash
# Create a zip archive of the project folder's files (Linux / macOS)
set -e
OUT="personal-ai-agent.zip"
echo "Creating ${OUT} ..."
# include only tracked project files present here
zip -r "${OUT}" README.md requirements.txt .env.example .gitignore main.py agent.py Dockerfile create_zip.py >/dev/null
echo "Created ${OUT}"
