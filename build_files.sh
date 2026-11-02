#!/bin/bash
set -e

python3 -m pip install -r requirements.txt --quiet || echo "pip install skipped: dependencies already installed by Vercel"
python3 manage.py collectstatic --noinput