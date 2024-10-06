# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Install system dependencies for OpenCV and other necessary packages
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsm6 \
    libxext6 \
    libgl1 \
    && apt-get clean

# Set the working directory in the container
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose port 5000
EXPOSE 5000

# Set environment variables
ENV FLASK_APP=api/index.py

# Run Flask
CMD ["flask", "run", "--host=0.0.0.0"]
