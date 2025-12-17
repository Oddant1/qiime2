.PHONY: all lint test install dev clean distclean

PYTHON ?= python
PREFIX ?= $(CONDA_PREFIX)

all: ;

lint:
	q2lint
	flake8

test: all
	QIIMETEST= pytest --doctest-modules

# for parallel, pip install pytest-xdist
mystery-stew: all
	MYSTERY_STEW= pytest rachis/tests/mystery_stew.py -n auto

install: all
	$(PYTHON) -m pip install -v .

dev: all
	pip install -e .

clean: distclean

distclean: ;
