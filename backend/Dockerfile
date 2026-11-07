FROM cgr.dev/chainguard/wolfi-base@sha256:8509ee4351a2e501b7f98201f2e2642396e82020c61a589cacdcfe74b9de46c1 AS dependencies

RUN apk add --no-cache python-3.13=3.13.18_git20261030-r0 py3.13-pip=26.2.2-r2 \
    && python3.13 -m venv /opt/venv
ENV PATH=/opt/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
WORKDIR /app
COPY requirements.lock ./
RUN pip install --no-cache-dir --require-hashes --only-binary=:all: -r requirements.lock \
    && pip check && pip uninstall --yes pip

FROM cgr.dev/chainguard/wolfi-base@sha256:8509ee4351a2e501b7f98201f2e2642396e82020c61a589cacdcfe74b9de46c1 AS runtime
RUN apk add --no-cache python-3.13=3.13.18_git20261030-r0

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH=/opt/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

WORKDIR /app

RUN addgroup -S -g 999 terrarag \
    && adduser -S -D -H -u 999 -G terrarag -h /app -s /bin/sh terrarag \
    && mkdir -p /data \
    && chown terrarag:terrarag /data

COPY pyproject.toml requirements.lock ./
COPY --from=dependencies /opt/venv /opt/venv
COPY app ./app

USER terrarag
RUN python -c "import ssl,sqlite3,tempfile; assert ssl.create_default_context().get_ca_certs(); d=tempfile.TemporaryDirectory(dir='/data'); db=sqlite3.connect(d.name+'/check.sqlite3'); assert db.execute('PRAGMA journal_mode=WAL').fetchone()[0]=='wal'; db.execute('CREATE VIRTUAL TABLE docs USING fts5(content)'); db.execute('INSERT INTO docs VALUES(?)',('maintenance',)); db.commit(); assert db.execute('SELECT content FROM docs WHERE docs MATCH ?',('maintenance',)).fetchone()[0]=='maintenance'; db.close(); d.cleanup()"
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
