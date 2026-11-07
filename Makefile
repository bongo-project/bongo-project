# Site maintenance. BONGO points at a checkout of github.com/bongo-project/bongo.
BONGO ?= ../bongo

# github-pages needs Ruby below 4.0, so these run it in a container.
RUBY_IMAGE ?= ruby:3.3
DOCKER_RUN = docker run --rm -v "$(CURDIR)":/site -w /site -p 4010:4010 $(RUBY_IMAGE) sh -c
BUNDLE_SETUP = bundle config set --local path vendor/bundle && bundle install --quiet

.PHONY: sync docs releases build serve docker-build docker-serve

sync: docs releases

docs:
	python3 scripts/sync_docs.py $(BONGO)

releases:
	python3 scripts/sync_releases.py $(BONGO)

build:
	bundle exec jekyll build

serve:
	bundle exec jekyll serve --port 4010

docker-build:
	$(DOCKER_RUN) '$(BUNDLE_SETUP) && bundle exec jekyll build'

docker-serve:
	$(DOCKER_RUN) '$(BUNDLE_SETUP) && bundle exec jekyll serve --host 0.0.0.0 --port 4010'
