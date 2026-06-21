# syntax=docker/dockerfile:1.7

FROM python:3.11-slim

ARG PIP_INDEX_URL=https://mirrors.cloud.tencent.com/pypi/simple/

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV PIP_ROOT_USER_ACTION=ignore

WORKDIR /app/backend

COPY backend/requirements-prod.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --index-url "${PIP_INDEX_URL}" -r requirements-prod.txt

COPY backend/app ./app

EXPOSE 8058

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8058"]
