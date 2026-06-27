# VERIFARMS backend — FastAPI streaming API (Milestones 2 & 3).
#
# Build context is ./backend (see docker-compose.yml), so paths below are
# relative to the backend/ directory.
#
#   docker build -t verifarms-backend ./backend
#   docker run --rm -p 8000:8000 --env-file .env verifarms-backend
#
# Or, with Neo4j, just: `docker compose up --build`.

FROM python:3.11-slim AS runtime

# - PYTHONUNBUFFERED: stream logs straight to the container (no buffering).
# - PYTHONDONTWRITEBYTECODE: no .pyc clutter in the image.
# - RELOAD=false: never run uvicorn's autoreloader in a container.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    HOST=0.0.0.0 \
    PORT=8000 \
    RELOAD=false

# System libraries the Python deps need at runtime:
#   - tesseract-ocr : the OCR engine pytesseract shells out to.
#   - libglib2.0-0  : required by opencv-python-headless.
RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (own layer) so they are cached across code changes.
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# Application code.
COPY . .

# Run as an unprivileged user — never as root in a container.
RUN useradd --create-home --uid 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Liveness: hit the app's own /health probe (no curl in slim images).
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]

# Run uvicorn directly (not `python main.py`) to keep reload off in production.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
