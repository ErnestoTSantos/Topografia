FROM python:3.11-slim

# Dependências necessárias para compilar ReportLab e para Pillow (PNG/JPEG)
RUN apt-get update && apt-get install -y \
    build-essential \
    libcairo2 \
    libcairo2-dev \
    libfreetype6-dev \
    libjpeg-dev \
    zlib1g-dev \
    liblcms2-dev \
    libwebp-dev \
    tk-dev \
    libharfbuzz-dev \
    libfribidi-dev \
    libtiff5-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app/

EXPOSE 8000

CMD ["python", "manage.py", "makemigrations"]
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
