FROM python:3.12-alpine

RUN apk update && apk upgrade --no-cache && \
    apk add --no-cache build-base gcc g++ gfortran openblas-dev lapack-dev

WORKDIR /app

COPY app/requirements.txt ./requirements.txt

RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

RUN adduser -D -H appuser \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
