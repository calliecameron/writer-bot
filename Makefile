.PHONY: all
all: lint

.PHONY: lint
lint:
	shellcheck *.sh
	shfmt -l -d -i 4 *.sh
	pylint --score n *.py
	flake8 '--filename=*.py,*.pyi'
	black --check .
	mypy --strict *.py

.PHONY: clean
clean:
	rm -rf *~ __pycache__
