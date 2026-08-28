FROM python:3.12-slim
WORKDIR /app
COPY telegram-shop/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY telegram-shop/ .
RUN mkdir -p /data && cp -r site templates /app/
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
