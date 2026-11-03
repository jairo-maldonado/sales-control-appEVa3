#!/bin/bash
set -e

python3 -m pip install -r requirements.txt --quiet || echo "pip install skipped: dependencies already installed by Vercel"

python3 -c "import rest_framework, rest_framework_simplejwt, corsheaders, whitenoise, dj_database_url, dotenv"
python3 manage.py check
python3 manage.py collectstatic --noinput