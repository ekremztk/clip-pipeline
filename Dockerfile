FROM python:3.11-slim-bookworm

# 1. Gerekli sistem paketleri
# libgl1 ve libglib2.0-0 -> OpenCV (PySceneDetect) için şarttır
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsndfile1 \
    git \
    build-essential \
    libfreetype6-dev \
    libjpeg-dev \
    zlib1g-dev \
    libavcodec-dev \
    libavformat-dev \
    libavutil-dev \
    libswresample-dev \
    libswscale-dev \
    pkg-config \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 2. Önce bağımlılıkları yükle (Cache avantajı için)
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir --upgrade yt-dlp

# 3. Kodları kopyala ve gerekli klasörleri oluştur
COPY backend/ .
RUN mkdir -p output temp_uploads

# 4. Railway ve Docker için dosya izinlerini ayarla
RUN chmod -R 777 output temp_uploads

EXPOSE 8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]