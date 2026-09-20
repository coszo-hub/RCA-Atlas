FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /service
RUN addgroup --system api && adduser --system --ingroup api api
COPY requirements.txt requirements-local-embeddings.txt ./
RUN pip install --no-cache-dir -r requirements-local-embeddings.txt
RUN mkdir -p /models && python -c "from fastembed import TextEmbedding; m=TextEmbedding(model_name='BAAI/bge-small-en-v1.5', cache_dir='/models'); next(iter(m.passage_embed(['model cache validation'])))" && chown -R api:api /models
COPY app ./app
COPY load_postgres.py ./load_postgres.py
ENV GRAPHRAG_MODEL_CACHE=/models GRAPHRAG_EMBEDDING_OFFLINE=true
USER api
EXPOSE 8000
CMD ["gunicorn", "app.factory:app", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "30", "--access-logfile", "-"]
