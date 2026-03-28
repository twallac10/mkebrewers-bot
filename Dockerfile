FROM python:3.9-slim

WORKDIR /app

# Install system dependencies for lxml and other compiled packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libxml2-dev \
    libxslt1-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    pytz pyarrow fastparquet

COPY scripts/ scripts/

ENV PYTHONPATH=/app

CMD ["bash"]
