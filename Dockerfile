# Downloads and sets up the Linux-based Python 3.10 engine automatically
FROM python:3.10

# Establish the container workspace
WORKDIR /app

# Install basic system build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all project structures (including pocketoptionapi_async and engine.py)
COPY . .

# Run your core script engine
CMD ["python", "engine.py"]
