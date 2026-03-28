FROM python:3.9-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libxml2-dev \
    libxslt1-dev \
    fonts-roboto \
    ruby-full \
    build-essential \
    zlib1g-dev \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    pytz pyarrow fastparquet geopandas tqdm \
    altair_saver altair-stiles vl-convert-python

# Install Ruby/Jekyll dependencies
COPY Gemfile Gemfile.lock ./
RUN gem install bundler && bundle install

ENV PYTHONPATH=/app

CMD ["bash"]
