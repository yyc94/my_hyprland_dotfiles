set shell := ["/usr/bin/env", "bash", "-eu", "-o", "pipefail", "-c"]

generate:
	@./scripts/config.py generate

check:
	@./scripts/config.py check

list:
	@./scripts/config.py list

test:
	@./scripts/config.py test

apply:
	@./scripts/config.py apply

rollback:
	@./scripts/config.py rollback

install:
	@./scripts/config.py install

migrate-variables:
	@./scripts/config.py migrate-variables
