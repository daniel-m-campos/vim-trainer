# make content   -> regenerate ../build from scratch (fetches pinned sources if needed)
# make test      -> pytest
# make review    -> interactive review of build/ exercises
.PHONY: content test review fetch

content:
	uv run vimtrainer-content build

fetch:
	uv run vimtrainer-content fetch

test:
	uv run pytest -q

review:
	uv run vimtrainer-content review
