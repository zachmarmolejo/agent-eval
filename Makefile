SPLIT ?= full
MODEL ?= fake
ARGS ?=

.PHONY: test eval smoke

test:
	uv run pytest -q

eval:
	uv run agent-eval run --split $(SPLIT) --model $(MODEL) $(ARGS)

smoke:
	uv run agent-eval run --split smoke --model fake
