# Use Python slim image as base
FROM python:3.10-slim-bullseye

# Set the working directory
WORKDIR /app

# Install only the necessary system dependencies for Pillow and numpy
RUN apt-get update && apt-get install -y --no-install-recommends \
    libopenblas0 \
    libjpeg62-turbo \
    zlib1g \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port for the application
EXPOSE 5000

# Run the application using Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]
