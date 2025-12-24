#!/usr/bin/env python3
"""
Cross-platform script to create personal-ai-agent.zip containing the project files.
Run: python create_zip.py
"""
import zipfile
import os

files = [
    "README.md",
    "requirements.txt",
    ".env.example",
    ".gitignore",
    "main.py",
    "agent.py",
    "Dockerfile",
]

out_name = "personal-ai-agent.zip"

with zipfile.ZipFile(out_name, "w", zipfile.ZIP_DEFLATED) as z:
    for f in files:
        if os.path.exists(f):
            z.write(f)
        else:
            print(f"Warning: {f} not found, skipping.")
print(f"Created {out_name}")
