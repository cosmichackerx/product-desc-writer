FROM python:3.11-slim

WORKDIR /usr/src/app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# For Apify platform, the Actor runner executes the default command,
# but for local runs we default to main.py
CMD ["python", "main.py"]
