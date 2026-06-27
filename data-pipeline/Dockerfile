# VERIFARMS data pipeline (Milestone 1) — synthetic generator + Neo4j loader.
#
# A one-off batch job, not a long-running service. Run it via compose:
#   docker compose run --rm loader                 # defaults: 1000 farmers, --reset
#   docker compose run --rm loader --farmers 200   # override args
#
# Build context is ./data-pipeline (see docker-compose.yml).

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Deps first for layer caching (faker, pandas, neo4j, python-dotenv).
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

# The script reads NEO4J_* from the environment (provided by compose).
# ENTRYPOINT fixes the command; CMD provides default args that callers override.
ENTRYPOINT ["python", "neo4j_loader.py"]
CMD ["--farmers", "1000", "--reset"]
