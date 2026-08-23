FROM node:22-bookworm AS glasskit-builder

ARG GLASSKIT_REV=4431554046e5ef4e03187469045182954dff746b
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/* \
    && git init /glasskit \
    && git -C /glasskit remote add origin https://github.com/RealComputer/GlassKit.git \
    && git -C /glasskit fetch --depth 1 origin "$GLASSKIT_REV" \
    && git -C /glasskit checkout --detach FETCH_HEAD \
    && cd /glasskit/cli/review-ui \
    && npm ci \
    && npm run build \
    && rm -rf node_modules

FROM mcr.microsoft.com/playwright/python:v1.54.0-noble

WORKDIR /app
COPY requirements.txt .
COPY --from=glasskit-builder /glasskit/cli /tmp/glasskit-cli
RUN rm -rf /tmp/glasskit-cli/review-ui \
    && apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir /tmp/glasskit-cli \
    && rm -rf /tmp/glasskit-cli \
    && git clone --depth 1 https://github.com/KaushikSiva/demo-ecom-store.git /workspace/regressionforge-demo-store
ARG REGRESSIONFORGE_SOURCE_REV=3
RUN test -n "$REGRESSIONFORGE_SOURCE_REV"
COPY regressionforge ./regressionforge
RUN mkdir -p /data /artifacts

ENV REGRESSIONFORGE_DATA=/data
ENV REGRESSIONFORGE_ARTIFACTS=/artifacts
ENV GLASSKIT_BIN=/usr/local/bin/glasskit
ENV TARGET_REPOSITORY=/workspace/regressionforge-demo-store
EXPOSE 8000
CMD ["uvicorn", "regressionforge.main:app", "--host", "0.0.0.0", "--port", "8000"]
