.PHONY: all
all: lint test

.PHONY: deps
deps: .deps-installed

.deps-installed: requirements.txt requirements-dev.txt
	pip install -r requirements.txt
	pip install -r requirements-dev.txt
	touch .deps-installed

requirements.txt: requirements.in pyproject.toml
	pip-compile -q

requirements-dev.txt: requirements-dev.in pyproject.toml
	pip-compile -q requirements-dev.in

.PHONY: lint
lint: deps
	ruff check .
	ruff format --diff .
	mypy --strict .

.PHONY: test
test: deps
	pytest --cov-report=term-missing --cov=writer_bot tests

.PHONY: clean
clean:
	rm -rf *~ __pycache__ writer_bot/*~ writer_bot/__pycache__ tests/*~ tests/__pycache__
