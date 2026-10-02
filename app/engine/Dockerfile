# Engine image. Build from the repo root: docker build -f app/engine/Dockerfile -t urbanpulse-engine .
# The context is filtered by app/engine/Dockerfile.dockerignore (BuildKit reads <Dockerfile>.dockerignore).
FROM python:3.10-slim

WORKDIR /srv
COPY app/engine/requirements.txt /srv/engine/requirements.txt
RUN pip install --no-cache-dir -r /srv/engine/requirements.txt
COPY app/engine /srv/engine
COPY models /srv/models

ENV PYTHONUTF8=1 PYTHONUNBUFFERED=1 TZ=Asia/Seoul MODELS_DIR=/srv/models
ENTRYPOINT ["python", "-m", "engine"]
