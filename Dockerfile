FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    MPLCONFIGDIR=/app/.matplotlib-cache \
    ARTIFACTS_DIR=/app/data/artifacts

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY main.py .
COPY src ./src

RUN mkdir -p /app/data/artifacts /app/.matplotlib-cache

EXPOSE 8000

CMD ["python3", "main.py", "--serve", "--host", "0.0.0.0", "--port", "8000"]
