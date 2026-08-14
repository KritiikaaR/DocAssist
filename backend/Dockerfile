# --- 1. Base image ---
# Every image starts FROM another one. Python 3.11 on stripped-down Debian.
# The full python:3.11 image is ~1GB; slim is ~150MB.
FROM python:3.10-slim

# --- 2. System packages ---
# Your OCR fallback needs two things that are NOT Python packages:
#   tesseract-ocr  — the engine pytesseract wraps
#   poppler-utils  — what pdf2image uses for PDF -> image
# A container starts empty, so anything your OS provided must be declared.
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# --- 3. Working directory ---
WORKDIR /app

# --- 4. Dependencies BEFORE code (the important bit) ---
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- 5. Application code ---
COPY . .

# --- 6. Documented port ---
EXPOSE 5000

# --- 7. Environment ---
ENV PYTHONUNBUFFERED=1

# --- 8. Start command ---
CMD ["python", "app.py"]