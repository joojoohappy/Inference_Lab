# Inference Lab app image (CPU). Build: docker build -t inference-lab .
# Run:  docker run --rm -p 127.0.0.1:8765:8765 -v inference-lab-data:/data inference-lab
#
# Single-user tool: there is no authentication. The app listens on 0.0.0.0 *inside* the container only so
# Docker can forward it (INFERENCE_LAB_ALLOW_REMOTE=1 below). Always publish on 127.0.0.1 as shown above;
# `-p 8765:8765` would expose it to your whole network.
FROM node:22-slim AS ui
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim
WORKDIR /app
# CPU wheels by default; override for a mirror or a CUDA build.
ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir torch --index-url ${TORCH_INDEX_URL}
# README.md is the package's long description (pyproject `readme`), so it is part of the build context.
COPY pyproject.toml README.md ./
COPY inference_lab ./inference_lab
RUN pip install --no-cache-dir -e ".[inference]"
COPY --from=ui /ui/dist ./frontend/dist
ENV INFERENCE_LAB_HOME=/data INFERENCE_LAB_HOST=0.0.0.0 INFERENCE_LAB_PORT=8765 INFERENCE_LAB_ALLOW_REMOTE=1
EXPOSE 8765
CMD ["inference-lab", "ui"]
