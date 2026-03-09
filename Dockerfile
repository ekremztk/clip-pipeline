FROM python:3.11-slim-bookworm

# 2. Sistem araçlarını kur (FFmpeg video işlemek için şart)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsndfile1 \
    git \
    && rm -rf /var/lib/apt/lists/*

# 3. Çalışma klasörünü ayarla
WORKDIR /app

# 4. BURASI KRİTİK: requirements.txt backend klasöründe olduğu için yolunu böyle verdik
COPY backend/requirements.txt .

# 5. Kütüphaneleri kur
RUN pip install --no-cache-dir -r requirements.txt

# 6. Tüm proje dosyalarını içeri kopyala
COPY . .

# 7. Uygulamayı başlat (Dış dizindeki main.py'yi çalıştırır)
CMD ["python", "main.py"]