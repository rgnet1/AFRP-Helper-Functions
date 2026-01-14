FROM python:3.10-slim-bullseye

# Create necessary directories and set permissions
RUN mkdir -p /config /app/downloads /app/logs /app/data /app/temp && \
    chmod -R 777 /app/logs /app/data /app/temp  # Ensure write permissions for logs, data, and temp

WORKDIR /app

# Create volumes for persistence
VOLUME ["/config", "/app/data", "/app/downloads", "/app/logs"]

# Set environment variable to indicate Docker environment
ENV DOCKER_CONTAINER=true

COPY requirements.txt .
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    python3-dev \
    pkg-config \
    libcairo2-dev \
    libopenblas0 \
    libjpeg62-turbo \
    zlib1g \
    && pip install --no-cache-dir -r requirements.txt \
    && apt-get purge -y build-essential python3-dev pkg-config libcairo2-dev \
    && apt-get autoremove -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy only necessary files, excluding config
COPY app.py .
COPY static/ static/
COPY templates/ templates/
COPY utils/ utils/

EXPOSE 5066

# Use a shell script to handle both the scheduler and web server
COPY docker-entrypoint.sh /
RUN chmod +x /docker-entrypoint.sh

CMD ["/docker-entrypoint.sh"]
