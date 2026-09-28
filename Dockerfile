FROM python:3.12-slim
ENV PYTHONUTF8=1 PYTHONUNBUFFERED=1
WORKDIR /app
EXPOSE 8765
CMD ["python", "scripts/docker_serve.py", "--host", "0.0.0.0", "--port", "8765"]