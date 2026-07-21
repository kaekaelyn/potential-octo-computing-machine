.PHONY: dev test lint venv backup

VENV := .venv
PYTHON := $(VENV)/bin/python

$(PYTHON):
	python3 -m venv $(VENV)
	$(PYTHON) -m pip install --upgrade pip -q
	$(PYTHON) -m pip install -r requirements-dev.txt -q

venv: $(PYTHON)

dev: venv
	$(PYTHON) -m vamp.wsgi

test: venv
	$(PYTHON) -m pytest

lint: venv
	$(PYTHON) -m ruff format --check .
	$(PYTHON) -m ruff check .
	$(PYTHON) scripts/check_pure_python_deps.py

backup: venv
	$(PYTHON) -m vamp.cli backup
