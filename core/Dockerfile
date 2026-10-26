# Контекст сборки - корень репозитория: образу нужны и core/, и frontend/
FROM python:3.12-slim
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-rus tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /srv/core
COPY core/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY core/ .
COPY frontend/ /srv/frontend/
ENV FRONTEND_DIR=/srv/frontend UPLOAD_DIR=/srv/uploads
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
