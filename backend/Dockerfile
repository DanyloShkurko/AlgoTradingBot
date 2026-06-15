# Backend image — FastAPI + bot runners. ARM64-friendly (Raspberry Pi 64-bit).
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# psycopg2-binary / cryptography / bcrypt ship aarch64 wheels, so no compiler
# needed on 64-bit Raspberry Pi OS. (On 32-bit you'd have to add build deps.)
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY app ./app

EXPOSE 8000

# IMPORTANT: single process only. The bot runners are in-process threads, so
# multiple workers would duplicate every bot and double its orders.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
