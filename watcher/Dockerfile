FROM python:3.10-alpine
WORKDIR /app
COPY watcher/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY watcher/watcher.py .
CMD ["python", "watcher.py"]
