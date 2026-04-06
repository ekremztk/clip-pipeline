FROM python:3.11-slim-bookworm

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
    libgles2 \
    libgl1 \
    libegl1 \
    libglib2.0-0 \
    curl \
    nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install wireproxy (userspace WireGuard → SOCKS5 proxy for WARP)
RUN curl -fsSL https://github.com/pufferffish/wireproxy/releases/download/v1.0.9/wireproxy_linux_amd64.tar.gz \
    | tar xz -C /usr/local/bin wireproxy \
    && chmod +x /usr/local/bin/wireproxy

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir --upgrade yt-dlp

COPY backend/ .
RUN mkdir -p output temp_uploads

RUN chmod -R 777 output temp_uploads
RUN chmod +x /app/start.sh

EXPOSE 8080

CMD ["/app/start.sh"]
