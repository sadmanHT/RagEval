ARG PYTHON_IMAGE=python:3.11.16-slim-bookworm

FROM ${PYTHON_IMAGE} AS wheel
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /build
COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m pip wheel --no-deps --wheel-dir /wheels .

FROM ${PYTHON_IMAGE} AS runtime
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
RUN groupadd --gid 10001 rageval \
    && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin rageval
COPY --from=wheel /wheels /tmp/wheels
RUN python -m pip install /tmp/wheels/*.whl \
    && rm -rf /tmp/wheels
WORKDIR /app
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=5s --timeout=3s --start-period=10s --retries=20 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=2).read()"]
CMD ["uvicorn", "rageval.serving.fixture_runtime:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]

FROM ${PYTHON_IMAGE} AS test
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 rageval \
    && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin rageval
WORKDIR /workspace
COPY . .
RUN python -m pip install -e '.[dev]'
RUN chown -R 10001:10001 /workspace
USER 10001:10001
CMD ["pytest", "-q"]
