# Dockerfile for hosting this repository on Railway (or any Docker host).
# The data in data/ is part of this repository, so it is copied into the image.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN useradd --create-home appuser && chown -R appuser /app
USER appuser

EXPOSE 8501
CMD ["sh", "railway-start.sh"]
