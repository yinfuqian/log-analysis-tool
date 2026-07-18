# 基础镜像均可替换为企业内部镜像；默认使用国内可访问的 Docker Hub 镜像代理。
ARG NODE_BASE_IMAGE=docker.m.daocloud.io/library/node:20-bookworm-slim
ARG NGINX_BASE_IMAGE=docker.m.daocloud.io/library/nginx:1.27-alpine

# 构建阶段固定 Node.js 20，并在生成静态文件前执行全部前端单元测试。
FROM ${NODE_BASE_IMAGE} AS build

WORKDIR /workspace
ARG NPM_REGISTRY=https://registry.npmmirror.com
ENV VUE_APP_BASE_URL=/api

COPY app/log-analyze/package.json app/log-analyze/package-lock.json ./
RUN npm config set registry "${NPM_REGISTRY}" \
    && npm ci

COPY app/log-analyze/ ./
RUN npm run test:unit -- --runInBand \
    && npm run build

# 生产阶段仅保留 Nginx 和静态文件，减少攻击面和镜像体积。
FROM ${NGINX_BASE_IMAGE}

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /workspace/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -qO- http://127.0.0.1/health || exit 1
