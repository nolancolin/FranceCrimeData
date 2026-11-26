PYTHON ?= python3
VENV := .venv
BIN := $(VENV)/bin

.PHONY: install data all test lint clean

install:
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install --quiet --upgrade pip
	$(BIN)/pip install --quiet -e ".[dev]"

data:
	$(BIN)/python -m delinquance obtain

all:
	$(BIN)/python -m delinquance all

test:
	$(BIN)/pytest -q

lint:
	$(BIN)/ruff check .
	$(BIN)/ruff format --check .

clean:
	rm -rf data
