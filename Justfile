set shell := ["/usr/bin/env", "bash", "-eu", "-o", "pipefail", "-c"]

generate:
	@./scripts/keymap.py generate

check:
	@./scripts/keymap.py check

list:
	@./scripts/keymap.py list

test:
	@./scripts/keymap.py test

apply:
	@./scripts/keymap.py apply

rollback:
	@./scripts/keymap.py rollback
