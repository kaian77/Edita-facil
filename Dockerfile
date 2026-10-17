# Edita Fácil na nuvem (Render, Railway, Fly.io…). Defina APP_PASSWORD para proteger o acesso.
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg fonts-inter libegl1 libgles2 libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

ENV HOST=0.0.0.0 PORT=8000 NO_BROWSER=1 PYTHONUNBUFFERED=1
EXPOSE 8000
# Os vídeos, a marca e as chaves ficam em /storage (monte um disco persistente nessa pasta).
CMD ["sh", "-c", "mkdir -p /storage/projects /storage/data /storage/music && rm -rf projects data music && ln -sfn /storage/projects projects && ln -sfn /storage/data data && ln -sfn /storage/music music && ln -sf /storage/config.json config.json && exec python -m server"]
