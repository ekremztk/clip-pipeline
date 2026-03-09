FROM python:3.11-slim-bookworm

# reportlab'ın derlenebilmesi için gerekli olan build-essential ve diğer kütüphaneler eklendi
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsndfile1 \
    git \
    build-essential \
    libfreetype6-dev \
    libjpeg-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Sadece backend klasörünü kopyala
COPY backend/ .
RUN mkdir -p output

EXPOSE 8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]