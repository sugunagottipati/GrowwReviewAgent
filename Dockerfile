FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir -e .

COPY Procfile ./

CMD ["sh", "-c", "exec python -m groww_pulse api --host 0.0.0.0 --port ${PORT:-8000}"]
