PYTHON := $(shell [ -x .venv/bin/python3 ] && echo .venv/bin/python3 || echo python3)

.PHONY: eval
eval:
	$(PYTHON) eval/run_eval.py