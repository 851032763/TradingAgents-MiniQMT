# Standalone Kronos microservice (CPU by default).
# The local model directories are copied into the image, so runtime does not
# need Hugging Face network access.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    KRONOS_HOST=0.0.0.0 \
    KRONOS_SERVICE_PORT=8101 \
    KRONOS_DEFAULT_MODEL=base

WORKDIR /app

COPY requirements.txt .

# Install the CPU wheels explicitly. The service also runs on GPU hosts, but
# this image is intentionally portable and does not require NVIDIA runtime.
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu \
        torch torchvision \
    && pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu \
        -r requirements.txt

COPY . .

EXPOSE 8101

HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8101/health', timeout=5)"

CMD ["python", "main.py"]
