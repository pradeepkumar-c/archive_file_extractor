FROM python:3.11-slim
WORKDIR /app

ENV PYTHONPATH=/app

COPY requirements.txt .
COPY requirements-dev.txt .

RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir -r requirements-dev.txt

COPY . .

EXPOSE 8080
CMD ["python", "app.py"]








