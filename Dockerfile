# Inference Lab app image (CPU). Build: docker build -t inference-lab .
# Run:  docker run --rm -p 127.0.0.1:8765:8765 -v inference-lab-data:/data inference-lab
# The container listens on 0.0.0.0 *inside* the container only so Docker can forward it;
# publish it on 127.0.0.1 as shown above. Not tested in the build environment (no Docker daemon there).
FROM node:22-slim AS ui
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim
WORKDIR /app
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
COPY pyproject.toml ./
COPY inference_lab ./inference_lab
RUN pip install --no-cache-dir -e ".[inference]"
COPY --from=ui /ui/dist ./frontend/dist
ENV INFERENCE_LAB_HOME=/data INFERENCE_LAB_HOST=0.0.0.0 INFERENCE_LAB_PORT=8765
EXPOSE 8765
CMD ["inference-lab", "ui"]
