.PHONY: all
all: lint test

.PHONY: lint
lint:
	pylint --score n --recursive y .
	flake8 '--filename=*.py,*.pyi'
	black --check .
	isort --check .
	mypy --strict .

.PHONY: test
test:
	pytest --cov-report=term-missing --cov=writer_bot tests

.PHONY: clean
clean:
	rm -rf *~ __pycache__ writer_bot/*~ writer_bot/__pycache__ tests/*~ tests/__pycache__
