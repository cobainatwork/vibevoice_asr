# Multi-stage build for production frontend
# Build context: repo root（與 backend.Dockerfile 對齊），可同時 COPY frontend/ 與 docker/nginx.conf
FROM node:20-alpine AS build

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci

COPY frontend/ .
RUN npm run build

FROM nginx:alpine

COPY --from=build /app/dist /usr/share/nginx/html
# nginx:alpine entrypoint 會把 templates/*.template 跑 envsubst 輸出到 conf.d/
# NGINX_ENVSUBST_FILTER_VARIABLES 限定只替換指定變數、避免誤替換 nginx 內建 $host 等
COPY docker/nginx.conf.template /etc/nginx/templates/default.conf.template
ENV NGINX_ENVSUBST_FILTER_VARIABLES=BACKEND_MAX_UPLOAD_MB
ENV BACKEND_MAX_UPLOAD_MB=500

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
