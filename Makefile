.PHONY: all
all: lint

.PHONY: lint
lint:
	shellcheck wordcount.sh
	shfmt -l -d -i 4 wordcount.sh
	pylint --score n --recursive y .
	flake8 '--filename=*.py,*.pyi'
	black --check .
	mypy --strict .

.PHONY: clean
clean:
	rm -rf *~ __pycache__
