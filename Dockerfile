# Kopybook CLI image:  docker build -t kopybook .   then   docker run --rm -v "$PWD:/work" kopybook layout my.cpy
FROM python:3.13-slim AS build
WORKDIR /src
COPY python/ ./python/
RUN pip wheel --no-cache-dir --no-deps -w /wheels ./python

FROM python:3.13-slim
LABEL org.opencontainers.image.title="Kopybook" \
      org.opencontainers.image.description="COBOL copybook to Kafka toolkit (CLI)" \
      org.opencontainers.image.version="0.1.3" \
      org.opencontainers.image.source="https://github.com/LupovichRan/kopybook" \
      org.opencontainers.image.licenses="Apache-2.0"
COPY --from=build /wheels /wheels
RUN pip install --no-cache-dir /wheels/*.whl && rm -rf /wheels && useradd -m -u 10001 kopybook
USER kopybook
WORKDIR /work
ENTRYPOINT ["kopybook"]
CMD ["--help"]
