FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    SOFFICE_PATH=soffice \
    MEGACMD_HOME=/tmp/megacmd-home

# LibreOffice: Office/PPT -> PDF
# ffmpeg: 多媒體 AI 出題
# MEGAcmd: MEGA 官方命令列客戶端（取代不相容 Python 3.12 的 mega.py）
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       libreoffice-impress ffmpeg qpdf fonts-noto-cjk wget ca-certificates gnupg procps \
    && wget -q https://mega.nz/linux/repo/Debian_12/amd64/megacmd-Debian_12_amd64.deb -O /tmp/megacmd.deb \
    && apt-get install -y /tmp/megacmd.deb \
    && rm -f /tmp/megacmd.deb \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY . .

RUN mkdir -p uploads tmp_convert static/slides data /tmp/megacmd-home \
    && chmod +x /app/run_web.sh

EXPOSE 5000
CMD ["bash", "run_web.sh"]
