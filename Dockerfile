FROM python:3.10-slim-bullseye

# Create necessary directories
RUN mkdir -p /config /app/downloads /app/logs

WORKDIR /app

# Create volume for config files
VOLUME ["/config"]

COPY requirements.txt .
RUN apt-get update && apt-get install -y --no-install-recommends \
    libopenblas0 \
    libjpeg62-turbo \
    zlib1g \
    && pip install --no-cache-dir -r requirements.txt

# Copy only necessary files, excluding config
COPY app.py .
COPY static/ static/
COPY templates/ templates/
COPY utils/ utils/

EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]
