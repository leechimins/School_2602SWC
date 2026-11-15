# 배포 이미지 하나: 프론트를 빌드해서 FastAPI가 같이 준다(주소 하나 → 쿠키·SSE가 로컬과 같다).
# Render가 서비스 환경변수를 빌드 인자로도 넘겨서 VITE_GOOGLE_CLIENT_ID가 빌드에 들어간다.

FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
ARG VITE_GOOGLE_CLIENT_ID=""
RUN npm run build

FROM python:3.13-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 STATIC_DIR=/app/static
COPY backend/requirements.txt ./
# pytest는 운영에 필요 없다
RUN grep -vE '^pytest' requirements.txt > req.txt && pip install --no-cache-dir -r req.txt
COPY backend/ ./
COPY --from=web /web/dist ./static
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
