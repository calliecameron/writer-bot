.PHONY: all
all: lint

.PHONY: lint
lint:
	shellcheck *.sh
	shfmt -l -d -i 4 *.sh
	pylint --score n *.py
	flake8 *.py
	black --check *.py
