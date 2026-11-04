# Site maintenance. BONGO points at a checkout of github.com/bongo-project/bongo.
BONGO ?= ../bongo

.PHONY: sync docs releases build serve

sync: docs releases

docs:
	python3 scripts/sync_docs.py $(BONGO)

releases:
	python3 scripts/sync_releases.py $(BONGO)

build:
	bundle exec jekyll build

serve:
	bundle exec jekyll serve --port 4010
