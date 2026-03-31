FROM python:3.14-slim

# Set up working directory
WORKDIR /app

# Copy project files
COPY . .

# Install dependencies
RUN pip install --no-cache-dir -r python-deps.txt

# Run the bot
CMD ["python", "main.py"]
