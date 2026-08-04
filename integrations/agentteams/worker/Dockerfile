FROM python:3.11-slim

WORKDIR /app
COPY claim_next.py ./claim_next.py
COPY worker_runner.py ./worker_runner.py
RUN useradd --create-home --uid 10002 worker
USER worker

ENTRYPOINT ["python", "/app/worker_runner.py"]
