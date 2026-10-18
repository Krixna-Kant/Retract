FROM node:22-alpine AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM python:3.11-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
COPY --from=web /web/dist web/dist
EXPOSE 8000
CMD ["python", "run.py", "--host", "0.0.0.0", "--no-build", "--no-docker"]
