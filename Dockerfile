FROM python:3.12-slim

# Install Stockfish 16
RUN apt-get update && \
    apt-get install -y stockfish && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Stockfish path on Debian/Ubuntu
ENV STOCKFISH_PATH=/usr/games/stockfish
ENV SF_THREADS=2
ENV SF_HASH=256

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
