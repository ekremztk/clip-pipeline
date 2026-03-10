FROM python:3.11-slim-bookworm

# Gerekli sistem paketleri ve FFmpeg kütüphane geliştirme paketleri
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsndfile1 \
    git \
    build-essential \
    libfreetype6-dev \
    libjpeg-dev \
    zlib1g-dev \
    # Yeni eklenenler: torchcodec ve ffmpeg bağımlılıkları için
    libavcodec-dev \
    libavformat-dev \
    libavutil-dev \
    libswresample-dev \
    libswscale-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Önce bağımlılıkları yükle
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# yt-dlp ve sorun çıkaran torch kütüphaneleri için ek önlem
RUN pip install --no-cache-dir --upgrade yt-dlp

# NOT: Eğer hata devam ederse, requirements.txt içindeki torch sürümünü 
# kontrol etmeliyiz. Şu anki hatan torch ve torchcodec uyuşmazlığı.

COPY backend/ .
RUN mkdir -p output

EXPOSE 8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]