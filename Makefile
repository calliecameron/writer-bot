.PHONY: all
all: lint test

.PHONY: lint
lint:
	shellcheck bin/wordcount.sh testdata/*.sh
	shfmt -l -d -i 4 bin/wordcount.sh testdata/*.sh
	pylint --score n --recursive y .
	flake8 '--filename=*.py,*.pyi'
	black --check .
	mypy --strict .

.PHONY: test
test:
	pytest tests

.PHONY: clean
clean:
	rm -rf *~ __pycache__
