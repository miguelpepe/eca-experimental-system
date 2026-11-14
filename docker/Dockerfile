FROM python:3.11-slim-bookworm
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg libsndfile1 libgomp1 git build-essential \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
COPY docker/constraints.txt ./docker/constraints.txt
RUN pip install -r requirements.txt -c docker/constraints.txt && pip check
COPY avatar_backend ./avatar_backend
COPY voices/warmup.wav voices/warmup-de.wav ./voices/
COPY docker/serve.py docker/check_gpu.py ./docker/
RUN mkdir -p uploads output_audio models
EXPOSE 8000
CMD ["python", "docker/serve.py"]
