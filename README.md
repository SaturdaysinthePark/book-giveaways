# Book Giveaways

A one-page board listing every currently-open Goodreads **print** book giveaway,
cover-forward, ranked by the odds of actually winning (`entrants ÷ copies`).
Search, sort, filter, click through to Goodreads to enter.

Live at **[sabtainkhan.com/book-giveaways](https://sabtainkhan.com/book-giveaways)**.

## How it works

There is no backend. `public/index.html` is a single self-contained file — inline
CSS, vanilla JS, no build step, no dependencies — that fetches a flat
`giveaways.json` sitting beside it and renders everything client-side.

The data is not live-scraped in the browser (that would be ~91 sequential
paginated calls against a CORS-restricted endpoint, per visitor). Instead
`.github/workflows/scrape.yml` runs `scripts/scrape.py` on a cron **twice daily
(06:00 and 18:00 UTC)**, commits the regenerated `giveaways.json`, and Netlify
publishes the new file. Static hosting, fresh data.

```
public/index.html            the entire app
public/giveaways.json        written by the scraper — do not hand-edit
public/_headers              Cache-Control: max-age=300 on giveaways.json
scripts/scrape.py            Goodreads AppSync GraphQL crawler
data/snapshots/*.jsonl       entry-velocity history (not read by the page)
.github/workflows/scrape.yml the twice-daily refresh
netlify.toml                 publish = public, no build command
```

## Running locally

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

Refresh the data (~91 requests, ~2 minutes):

```bash
.venv/bin/python scripts/scrape.py
```

Serve the page — `giveaways.json` must be fetched over HTTP, not `file://`:

```bash
python3 -m http.server 8123 --directory public
```

## The scraper

Hits Goodreads' public AppSync GraphQL endpoint directly — no HTML parsing, no
login, no cookies. The API key is a public one lifted from their JS bundle; when
it rotates, `discover_api_key()` re-finds it from the page bundle automatically.
The server caps pages at 15 rows regardless of what you ask for, so a full run is
~91 requests with a 1s delay between them.

It **refuses to write** if a run collects less than 90% of the API-reported
total, so a mid-crawl network failure fails the job rather than silently
publishing a truncated board.

```bash
python scripts/scrape.py --out /tmp/g.json --snapshots '' --max-pages 3
```

`data/snapshots/` accumulates one `{ts, slug, entries}` line per giveaway per run.
Nothing reads it yet — it exists so entry-velocity ("filling up fast") can be
added later, and it can't be backfilled, so it's collected from day one. Files are
dated so git stores each day once instead of re-storing one ever-growing blob.

## Deployment

Netlify builds from this repo with publish directory `public` and **no build
command**. Every data commit from the Action triggers a republish.

The site is served at `sabtainkhan.com/book-giveaways` by a proxy rule in the
separate personal-site repo (`SaturdaysinthePark/sabtainkhan`), not by a custom
domain here:

```toml
[[redirects]]
  from = "/book-giveaways"
  to = "/book-giveaways/"
  status = 301
  force = true

[[redirects]]
  from = "/book-giveaways/*"
  to = "https://<this-site>.netlify.app/:splat"
  status = 200
  force = true
```

The trailing-slash redirect is load-bearing. Without it, a visit to
`/book-giveaways` (no slash) makes the page's relative `fetch("giveaways.json")`
resolve to `sabtainkhan.com/giveaways.json` and 404.

## Design

Built from a high-fidelity handoff. Two places where the implementation departs
from the spec as literally written, both deliberate:

- **Two columns on phones.** The spec requires "2 columns on a 480px phone — do
  not drop to 1 column", but its own tokens (`minmax(212px, 1fr)`, 22px gap,
  28px gutter) need 446px of content width, and a 480px phone has 424px. Below
  700px — the width at which auto-fill would stop giving a third column anyway —
  the grid is pinned to `repeat(2, 1fr)`, so the two rules meet seamlessly.
- **Stat strip gutter on wrap.** The spec gives the first stat cell no left
  padding and the rest 16px. When the strip wraps on narrow screens that indents
  the second row away from the 28px page gutter every other section aligns to, so
  below 619px the strip is pinned 2-up with the left column flush.

The cover `<a>` carries `tabindex="-1"` and `aria-hidden="true"` because the
title link immediately below it points at the same URL — without that, keyboard
and screen-reader users hit three links per card, two of them identical.
