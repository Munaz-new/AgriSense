FROM python:3.14-slim

ENV AGRISENSE_ENV=production \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/tmp

WORKDIR /app
COPY backend/requirements-production.txt /app/backend/requirements-production.txt
RUN python -m pip install --no-cache-dir torch==2.14.0 torchvision==0.29.0 \
      --index-url https://download.pytorch.org/whl/cpu \
    && python -m pip install --no-cache-dir -r backend/requirements-production.txt

COPY backend/app /app/backend/app
COPY backend/serve.py backend/backup.py backend/restore_demo.py /app/backend/
COPY model/agrisense_model /app/model/agrisense_model
COPY model/configs/tomato.json /app/model/configs/tomato.json

RUN mkdir -p /data /tmp && chown -R 10001:10001 /app /data /tmp
USER 10001:10001

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=300s --retries=3 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.getenv('PORT', '8000') + '/ready', timeout=4)"

CMD ["python", "-m", "backend.serve"]
