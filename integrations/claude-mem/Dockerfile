# Claude-Mem 13.15.3 server image, pinned to the audited upstream revision.
# Source: https://github.com/thedotmack/claude-mem/tree/e2d1df569a8f04075d40e92461128ece7cf04c82
FROM node:20-bookworm

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      git curl ca-certificates unzip jq less procps uuid-runtime sqlite3 \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

ARG BUN_VERSION=1.3.12
ENV BUN_INSTALL=/usr/local/bun
RUN curl -fsSL https://bun.sh/install | bash -s "bun-v${BUN_VERSION}" \
 && chmod -R a+rX /usr/local/bun
ENV PATH=/usr/local/bun/bin:/usr/local/share/npm-global/bin:${PATH}

ARG UV_VERSION=0.11.7
ENV UV_INSTALL_DIR=/usr/local/bin
RUN set -eux; \
    curl -LsSf "https://astral.sh/uv/${UV_VERSION}/install.sh" | sh; \
    chmod a+rX /usr/local/bin/uv /usr/local/bin/uvx 2>/dev/null || true

RUN mkdir -p /usr/local/share/npm-global \
 && chown -R node:node /usr/local/share/npm-global
ENV NPM_CONFIG_PREFIX=/usr/local/share/npm-global

ARG CLAUDE_MEM_REV=e2d1df569a8f04075d40e92461128ece7cf04c82
RUN git init /tmp/claude-mem \
 && git -C /tmp/claude-mem remote add origin https://github.com/thedotmack/claude-mem.git \
 && git -C /tmp/claude-mem fetch --depth 1 origin "$CLAUDE_MEM_REV" \
 && git -C /tmp/claude-mem checkout --detach FETCH_HEAD \
 && mkdir -p /opt/claude-mem \
 && cp -a /tmp/claude-mem/plugin/. /opt/claude-mem/ \
 && cp /tmp/claude-mem/docker/claude-mem/entrypoint.sh /usr/local/bin/claude-mem-entrypoint \
 && chmod +x /usr/local/bin/claude-mem-entrypoint \
 && rm -rf /tmp/claude-mem \
 && chown -R node:node /opt/claude-mem

USER node
RUN cd /opt/claude-mem \
 && npm install --omit=dev --legacy-peer-deps

USER root
RUN mkdir -p /home/node/.claude /home/node/.claude-mem /data/claude-mem \
 && chown -R node:node /opt/claude-mem /home/node/.claude /home/node/.claude-mem /data/claude-mem

USER node
WORKDIR /home/node
ENV CLAUDE_MEM_CONTAINER_MODE=server
ENV CLAUDE_MEM_RUNTIME=server-beta
ENTRYPOINT ["/usr/local/bin/claude-mem-entrypoint"]
CMD []
