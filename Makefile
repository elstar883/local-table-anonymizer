PY ?= python3
PORT ?= 8765

.PHONY: install demo run test e2e validate check clean

install:
	$(PY) -m pip install -r requirements-dev.txt

demo:
	$(PY) scripts/make_demo.py 5000 demo.csv

run:
	$(PY) main.py $(PORT)

test:
	$(PY) tests/test_lta.py

e2e: demo
	bash scripts/e2e.sh

validate:
	$(PY) scripts/validate.py

check: validate test e2e

clean:
	rm -f demo.csv uitest_anon.csv uitest_restored.csv
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
	find . -name '*.pyc' -delete
