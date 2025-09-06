#!/usr/bin/env bash
set -euo pipefail

# Validate the SAM/CloudFormation template
sam validate

# Quick sanity checks (optional but helpful)
test -f analyze_fn/app.py || { echo "Missing analyze_fn/app.py"; exit 1; }
test -f site/upload.html || { echo "Missing site/upload.html"; exit 1; }
test -f data/jobs.json   || { echo "Missing data/jobs.json"; exit 1; }

echo "Template valid. Files present. Ready to deploy."
