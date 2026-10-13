FROM python:3.12-slim-bookworm

RUN apt-get update \
    && apt-get upgrade -y \
        util-linux \
        libacl1 \
        libncurses6 \
        libsystemd0 \
        perl-base \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY app/requirements.txt ./requirements.txt

RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

RUN useradd --system --no-create-home appuser \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
