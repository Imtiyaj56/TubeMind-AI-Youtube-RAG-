FROM python:3.10-slim

# Install system dependencies (ffmpeg is strictly required for yt-dlp and faster-whisper)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/*

# Set up a new user named "user" with user ID 1000
# Hugging Face Spaces require running containers as a non-root user for security.
RUN useradd -m -u 1000 user
USER user

# Set home to the user's home directory
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

# Set the working directory to the user's home directory
WORKDIR $HOME/app

# Copy the requirements file and install dependencies
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY --chown=user . $HOME/app

# Hugging Face Spaces route external traffic to port 7860 by default
EXPOSE 7860

# Command to run our FastAPI server
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]
