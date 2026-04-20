# GPU Pipeline Service — Cloud Run L4
# Runs S08 (export), S09 (reframe), S10 (captions) with NVENC acceleration
#
# Build from monorepo root:
#   docker build -f gpu-service/Dockerfile -t gpu-pipeline .
FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# System deps: FFmpeg with NVENC, fonts, build tools
RUN apt-get update && apt-get install -y \
    software-properties-common \
    && add-apt-repository ppa:deadsnakes/ppa \
    && apt-get update && apt-get install -y \
    python3.11 \
    python3.11-venv \
    python3.11-dev \
    python3-pip \
    ffmpeg \
    libsndfile1 \
    build-essential \
    libfreetype6-dev \
    libjpeg-dev \
    zlib1g-dev \
    pkg-config \
    libglib2.0-0 \
    libgl1 \
    curl \
    fonts-open-sans \
    && rm -rf /var/lib/apt/lists/*

# Install Montserrat font
RUN mkdir -p /usr/share/fonts/truetype/montserrat /root/.fonts \
    && curl -fsSL -o /usr/share/fonts/truetype/montserrat/Montserrat-Bold.ttf \
       "https://github.com/JulietaUla/Montserrat/raw/master/fonts/ttf/Montserrat-Bold.ttf" \
    && curl -fsSL -o /usr/share/fonts/truetype/montserrat/Montserrat-Regular.ttf \
       "https://github.com/JulietaUla/Montserrat/raw/master/fonts/ttf/Montserrat-Regular.ttf" \
    && cp /usr/share/fonts/truetype/montserrat/*.ttf /root/.fonts/ \
    && fc-cache -fv

# Make python3.11 the default
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1 \
    && update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1

# Upgrade pip
RUN python3.11 -m pip install --no-cache-dir --upgrade pip setuptools wheel

WORKDIR /app

# Install Python deps (cached layer — only rebuilds when requirements change)
COPY gpu-service/requirements-gpu.txt .
RUN python3.11 -m pip install --no-cache-dir -r requirements-gpu.txt

# Pre-download YOLO face model (avoids cold-start download delay)
RUN mkdir -p /app/models \
    && curl -fsSL -o /app/models/yolov8l-face.pt \
       "https://huggingface.co/arnabdhar/YOLOv8-Face-Detection/resolve/main/model.pt" \
    && ls -lh /app/models/yolov8l-face.pt

# Copy only the modules needed for S08-S09-S10 from backend
COPY backend/app/__init__.py ./app/__init__.py
COPY backend/app/config.py ./app/config.py
COPY backend/app/services/__init__.py ./app/services/__init__.py
COPY backend/app/services/supabase_client.py ./app/services/supabase_client.py
COPY backend/app/services/r2_client.py ./app/services/r2_client.py
COPY backend/app/services/deepgram_client.py ./app/services/deepgram_client.py
COPY backend/app/services/gemini_client.py ./app/services/gemini_client.py
COPY backend/app/captions/ ./app/captions/
COPY backend/app/reframe/ ./app/reframe/
COPY backend/app/pipeline/__init__.py ./app/pipeline/__init__.py
COPY backend/app/pipeline/steps/__init__.py ./app/pipeline/steps/__init__.py
COPY backend/app/pipeline/steps/s08_export.py ./app/pipeline/steps/s08_export.py
COPY backend/app/pipeline/steps/s09_reframe.py ./app/pipeline/steps/s09_reframe.py
COPY backend/app/pipeline/steps/s10_captions.py ./app/pipeline/steps/s10_captions.py

# Copy GPU service entry point + stubs
COPY gpu-service/app/main.py ./app/gpu_main.py
COPY gpu-service/app/director/ ./app/director/

RUN mkdir -p output temp_uploads && chmod -R 777 output temp_uploads

EXPOSE 8080

CMD ["python3.11", "-m", "uvicorn", "app.gpu_main:app", "--host", "0.0.0.0", "--port", "8080", "--timeout-keep-alive", "600"]
