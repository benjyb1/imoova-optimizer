FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Playwright is needed for Imoova scraping (not flights)
RUN playwright install chromium --with-deps
COPY . .
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "10000"]
