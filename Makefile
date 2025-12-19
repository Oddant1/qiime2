.PHONY: all lint test install dev clean distclean

PYTHON ?= python
PREFIX ?= $(CONDA_PREFIX)

all: ;

lint:
	uv run nox -s lint

test: all
	uv run nox -t test-max

# for parallel, pip install pytest-xdist
mystery-stew: all
	MYSTERY_STEW= pytest rachis/tests/mystery_stew.py -n auto

install: all
	$(PYTHON) -m pip install -v .

dev: all
	pip install -e .

clean: distclean

distclean: ;
