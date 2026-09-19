FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    SOFFICE_PATH=soffice \
    MEGACMD_HOME=/tmp/megacmd-home

# Web image runtime dependencies:
# - LibreOffice Writer/Calc/Impress: synchronous compatibility upload and text/preview extraction for
#   Word, spreadsheet, presentation, and matching OpenDocument formats accepted by the Web runtime.
# - ffmpeg: Groq video-question generation extracts audio and representative frames in the Web process.
# - qpdf: optional PDF linearization on the synchronous compatibility upload path.
# - MEGAcmd: Web-side MEGA storage reads/downloads/deletes/status checks, not only worker uploads.
# The base image is pinned to Debian 12/bookworm because the MEGAcmd package below is the Debian 12 build.
# Background material conversion itself is owned by the local worker.  Do not remove these packages
# from the Web image until the remaining synchronous/AI call sites are migrated away from them.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       libreoffice-writer libreoffice-calc libreoffice-impress \
       ffmpeg qpdf fonts-noto-cjk wget ca-certificates gnupg procps \
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
