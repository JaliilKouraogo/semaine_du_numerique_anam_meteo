FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Dépendances système : OCR (tesseract), rendu OpenCV (libgl), conversion PDF (poppler)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        tesseract-ocr \
        libgl1 \
        libglib2.0-0 \
        poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install --upgrade pip && \
    pip install --no-cache-dir \
        requests \
        beautifulsoup4 \
        pymupdf \
        pillow \
        opencv-python \
        numpy \
        pytesseract \
        fastapi \
        "uvicorn[standard]" \
        sqlalchemy

COPY . /app

CMD ["bash"]
