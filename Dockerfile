FROM python:3.10-slim
WORKDIR /app
#COPY HelloWorld.py .
#CMD ["python", "-u", "HelloWorld.py"]

COPY app.py .
COPY requirements.txt .
COPY config.json .
RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8080
CMD ["python", "app.py"]