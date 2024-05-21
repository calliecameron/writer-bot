.PHONY: all
all: lint test

.PHONY: lint
lint:
	ruff check .
	ruff format --diff .
	mypy --strict .

.PHONY: test
test:
	pytest --cov-report=term-missing --cov=writer_bot tests

.PHONY: clean
clean:
	rm -rf *~ __pycache__ writer_bot/*~ writer_bot/__pycache__ tests/*~ tests/__pycache__
