PY := .venv/bin/python

.PHONY: venv corpus test test-python test-java package it bench docs demo docker
venv:
	python3 -m venv .venv && .venv/bin/pip install -q pytest fastavro jsonschema kafka-python mkdocs-material && \
	.venv/bin/pip install -q -e python
corpus:
	$(PY) corpus/generator/gen_corpus.py
test: test-python test-java
test-python:
	cd python && ../$(PY) -m pytest -q tests
test-java:
	cd java && mvn -q -B test
package:
	cd java && mvn -q -B package -DskipTests
it: package
	cd integration && docker compose up -d && cd .. && $(PY) integration/roundtrip.py
bench:
	cd java && mvn -q -B test-compile && java -cp "target/classes:target/test-classes:$$(mvn -q -B dependency:build-classpath -Dmdep.outputFile=/dev/stdout)" dev.kopybook.bench.Bench ../corpus
docs:
	.venv/bin/mkdocs build --strict -d site
demo:
	$(PY) docs/demo/make_demo.py --gif
docker:
	docker build -t kopybook:dev . && docker run --rm -v "$$PWD/corpus:/data" kopybook:dev layout /data/copybooks/30_customer_master.cpy
