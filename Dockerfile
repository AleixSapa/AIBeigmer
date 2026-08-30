FROM nginx:1.27-alpine

RUN apk add --no-cache python3 py3-pip

WORKDIR /app
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir --break-system-packages -r /app/backend/requirements.txt

COPY backend/ /app/backend/
COPY frontend/ /usr/share/nginx/html/
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY docker/start.sh /start.sh
RUN chmod +x /start.sh

ENV PYTHONPATH=/app
EXPOSE 80
CMD ["/start.sh"]
