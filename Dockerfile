FROM python:3.10-slim

# Install system dependencies (needed for Camelot)
RUN apt-get update && \
    apt-get install -y ghostscript && \
    apt-get clean

# Set working directory
WORKDIR /app

# Copy all files
COPY . .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose port
EXPOSE 8080

# Start FastAPI
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port $PORT"]
