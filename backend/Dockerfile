FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN groupadd --system terrarag \
    && useradd --system --gid terrarag --home-dir /app terrarag \
    && mkdir -p /data \
    && chown terrarag:terrarag /data

COPY pyproject.toml requirements.lock ./
COPY app ./app
RUN pip install --no-cache-dir --require-hashes -r requirements.lock \
    && pip install --no-cache-dir --no-deps .

USER terrarag
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
