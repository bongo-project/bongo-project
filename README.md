# bongo-project.org

Source of the website at <https://bongo-project.org>. GitHub Pages builds it
with Jekyll from the `gh-pages` branch. The `CNAME` file sets the domain.

The software itself is at <https://github.com/bongo-project/bongo>.

## Layout

| Path | Content |
|------|---------|
| `index.html` | Home page |
| `docs/` | Operator documentation, copied from the code repository (generated) |
| `releases/index.html` | Release notes, rendered from `_data/releases.json` (generated) |
| `history/` | Pages of the original C and Python project (2007-2010), kept as written |
| `_layouts/` | `default` (page shell), `doc` (docs with sidebar), `history` (archive banner) |
| `_includes/` | Header, footer, inline logo, heading anchors |
| `assets/` | CSS, Geist fonts (SIL OFL, see `assets/fonts/OFL.txt`), logo, favicon, screenshots |
| `images/` | Images used by the history pages |

Old `/Documentation/...` URLs redirect to `/history/...` through
`jekyll-redirect-from`, which GitHub Pages supports.

## Refreshing docs and release notes at each release

Both scripts read a local checkout of the code repository (default `../bongo`).
Check out the release tag there first.

```bash
make sync BONGO=../bongo     # runs both scripts below
make docs                    # scripts/sync_docs.py: docs/*.md and _data/docs.yml
make releases                # scripts/sync_releases.py: _data/releases.json from the v* tags
```

`scripts/sync_docs.py` holds the list of published documents and their sidebar
order. It adds front matter, rewrites links between published docs to site URLs
and every other repository-relative link to a GitHub URL, and wraps each page in
`{% raw %}` so that template syntax in the docs is not run as Liquid. Edit the
`DOCS` list there to publish another document; do not edit `docs/*.md` by hand.

`scripts/sync_releases.py` groups tags by minor version. Each minor release
shows its full tag message; patch releases are listed under it, collapsed.
Lightweight tags and tags without notes show the version and date only.

After a release, also set `latest_release` in `_config.yml`.

## Building locally

The `Gemfile` pins the `github-pages` gem so a local build matches the live one.
GitHub builds the live site with its own versions and ignores `Gemfile.lock`. The
current versions are at <https://pages.github.com/versions.json>. When that file
moves on, change the pin in the `Gemfile` and regenerate the lock.

`github-pages` needs Ruby below 4.0. With Docker, no local Ruby is needed:

```bash
make docker-serve    # http://localhost:4010
make docker-build    # writes _site/
```

With a local Ruby 3.3:

```bash
bundle config set --local path vendor/bundle
bundle install
bundle exec jekyll serve --port 4010
```

Use only features GitHub Pages supports: kramdown with GFM input, Rouge, and the
`jekyll-redirect-from`, `jekyll-sitemap` and `jekyll-seo-tag` plugins. No
custom plugins, no JavaScript, no CDN: fonts and styles are served from
`assets/`.
