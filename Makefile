.PHONY: all lint test install dev clean distclean

PYTHON ?= python
PREFIX ?= $(CONDA_PREFIX)

all: ;

lint:
	uv run nox -s lint

test: all
	uv run nox -t test-max

mystery-stew: all
	uv run nox -s test_mystery_stew

install: all
	$(PYTHON) -m pip install --no-deps -v .

dev: all
	pip install -e .

clean: distclean

distclean: ;
