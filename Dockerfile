FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN addgroup --system app && adduser --system --ingroup app app
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --retries 10 --timeout 120 -r requirements.txt

COPY app ./app
COPY scripts ./scripts
COPY eval ./eval
COPY tests ./tests
COPY config ./config

USER app
EXPOSE 8010
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8010"]

