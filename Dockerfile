# Use an official Python runtime as a parent image
FROM python:3.10

# Set the working directory in the container
WORKDIR /app

# Expose port 8000 for FastAPI
EXPOSE 8000

# Install dependencies
RUN pip install --upgrade pip

# Copy dependencies first for efficient Docker caching
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy the rest of the application code
COPY . /app/

# Run the FastAPI application using Uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
