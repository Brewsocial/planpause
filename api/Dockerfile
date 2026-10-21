FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 && rm -rf /var/lib/apt/lists/*
WORKDIR /srv
COPY engine /srv/engine
COPY api /srv/api
RUN pip install --no-cache-dir /srv/engine fastapi "uvicorn[standard]" python-multipart httpx
WORKDIR /srv/api
ENV PLANPAUSE_DATA=/data
EXPOSE 8000
# Hoster wie Render geben den Port über $PORT vor
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
