# Hardened Dockerfile for Broker Gateway & Algo Pods

FROM python:3.12-alpine AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Non-root User Isolation (UID 10001:10001)
RUN addgroup -g 10001 omssgroup && \
    adduser -u 10001 -G omssgroup -D -h /app omsuser

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app/oms_project

RUN chown -R 10001:10001 /app && \
    chmod -R 550 /app/oms_project

USER 10001:10001

EXPOSE 8000

CMD ["python", "-m", "pytest", "oms_project/tests"]
