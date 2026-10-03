# BlueOS extension "tides": honest water levels for Issyk-Kul, its
# rivers and the Caspian.  The image is a slim Python runtime with two
# pure-Python wheels only, so it stays small on the ROV computer.
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY requirements.txt .
# An optional build secret "pipca" lets a build behind a TLS-inspecting
# proxy trust its CA without baking the certificate into the image.
RUN --mount=type=secret,id=pipca \
    if [ -s /run/secrets/pipca ]; then \
      export PIP_CERT=/run/secrets/pipca; fi \
    && pip install --no-cache-dir -r requirements.txt \
    && useradd --system --uid 10001 --no-create-home tides
COPY app ./app
COPY data ./data

# The test stage is built only on request (--target test), so pytest
# never ships in the extension image.
FROM base AS test
COPY requirements-dev.txt .
RUN --mount=type=secret,id=pipca \
    if [ -s /run/secrets/pipca ]; then \
      export PIP_CERT=/run/secrets/pipca; fi \
    && pip install --no-cache-dir -r requirements-dev.txt
COPY tests ./tests
USER tides
CMD ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"]

FROM base AS runtime
USER tides
EXPOSE 9050

LABEL version="0.1.0"
LABEL permissions='{\
  "ExposedPorts": {"9050/tcp": {}},\
  "HostConfig": {\
    "PortBindings": {"9050/tcp": [{"HostPort": "9050"}]}\
  }\
}'
LABEL authors='[{"name": "Leonidy431", "email": ""}]'
LABEL company='{\
  "about": "ROV research on Issyk-Kul and diving instruction",\
  "name": "Leonidy431",\
  "email": ""\
}'
LABEL type="tool"
LABEL tags='["water", "lake", "sea", "river", "tide", "rov"]'
LABEL readme="https://raw.githubusercontent.com/Leonidy431/tides/main/README.md"
LABEL links='{"source": "https://github.com/Leonidy431/tides"}'
LABEL requirements="core >= 1.1"

CMD ["python", "-m", "uvicorn", "app.main:app", \
     "--host", "0.0.0.0", "--port", "9050"]
