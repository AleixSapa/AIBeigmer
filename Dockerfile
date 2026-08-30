# AIBeigmer - production container for Dokploy
FROM nginx:1.27-alpine

# Frontend lives in its own directory.
COPY frontend/ /usr/share/nginx/html/

# Nginx config also serves the SPA and proxies /api to the FastAPI service.
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
