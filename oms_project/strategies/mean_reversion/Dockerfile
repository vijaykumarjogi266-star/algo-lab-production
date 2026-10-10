# Hardened Strategy Pod Dockerfile for Mean Reversion Bot

FROM python:3.12-alpine AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Set user to 10001:10001
RUN addgroup -g 10001 omssgroup && \
    adduser -u 10001 -G omssgroup -D -h /app omsuser

WORKDIR /app

# Copy application and requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app/oms_project

# Permissions
RUN chown -R 10001:10001 /app && \
    chmod -R 550 /app/oms_project

USER 10001:10001

CMD ["python", "-m", "oms_project.strategies.mean_reversion.mean_reversion_strat"]
