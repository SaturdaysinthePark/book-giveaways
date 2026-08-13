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
public/favicon.svg           the raffle-ticket mark — the one icon source
public/favicon-*.png         rasterised from favicon.svg — do not hand-edit
public/apple-touch-icon.png  rasterised from favicon.svg — do not hand-edit
public/og.png                rasterised from tools/og.html — do not hand-edit
tools/og.html                share-card layout (1200x630)
tools/make-assets.py         renders the icons and the share card to PNG
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
  to = "https://book-giveaways.netlify.app/index.html"
  status = 200
  force = true

[[redirects]]
  from = "/book-giveaways/*"
  to = "https://book-giveaways.netlify.app/:splat"
  status = 200
  force = true
```

Both forms proxy straight through — there is no 301 between them, because
Netlify ignores trailing slashes when matching and a `/book-giveaways` →
`/book-giveaways/` rule matches its own target and loops forever.

**So nothing here may use a bare relative path.** At `/book-giveaways` with no
trailing slash the browser reads `book-giveaways` as a filename and resolves
siblings against the domain root, landing on the personal site instead. The data
fetch works around it in JS (`dataUrl()` resolves against the page's own
directory); the `<head>` can't, so the icon, share-card and canonical URLs are
absolute `https://sabtainkhan.com/book-giveaways/…`. Those work from the proxy
and from the raw `book-giveaways.netlify.app` origin alike.

## Design

Built from a high-fidelity handoff. Three places where the implementation departs
from the spec as literally written, all deliberate:

- **No duotone cover treatment.** The spec stacks three layers on every cover:
  `grayscale(1)`, a band-coloured tint in `mix-blend-mode:color`, and a paper
  scanline. In practice the texture fought the artwork — it was softened twice
  (scanline 2px/55% → 4px/22%, tint 90% → 75%) and still read as noise, so all
  three layers came out. Covers show their real artwork and the odds colour moved
  off the image into the layout: an 8px hard offset shadow on the cover, plus the
  rank chip and the odds figure, all reading `--band` off the card. The "Full
  colour" toggle went with it, having nothing left to toggle.
- **Two columns on phones.** The spec requires "2 columns on a 480px phone — do
  not drop to 1 column", but its own tokens (`minmax(212px, 1fr)`, 22px gap,
  28px gutter) need 446px of content width, and a 480px phone has 424px. Below
  700px — the width at which auto-fill would stop giving a third column anyway —
  the grid is pinned to `repeat(2, 1fr)`, so the two rules meet seamlessly.
- **Stat strip gutter on wrap.** The spec gives the first stat cell no left
  padding and the rest 16px. When the strip wraps on narrow screens that indents
  the second row away from the 28px page gutter every other section aligns to, so
  below 619px the strip is pinned 2-up with the left column flush.

### Icon and share card

The mark is a raffle ticket with an open book on it: `public/favicon.svg`, drawn
on a 32-unit grid, accent tile with a paper ticket. It is the only icon source —
the PNGs and the share card are rendered from it and from `tools/og.html` by

```bash
python3 tools/make-assets.py
```

which shells out to headless Chrome (macOS path) and downsamples with Pillow.
Both assets render at a multiple of their final size and get scaled down —
the icon from a 512px master, the card at `--force-device-scale-factor=2` — so
the punched scallops, the dashed perforation and the hairline gaps in the stat
strip don't alias. Rerun it after editing `favicon.svg` or `og.html`, and commit
the PNGs; the site itself stays build-step free.

The card is the same raffle ticket as the hero, with the same tokens and the
same radial-gradient scallops, scaled about 1.85x because a timeline shows it at
a third of its size. Two deliberate departures from the hero: it is punched only
down the right edge, where the stub is and where the ticket would actually be
torn — punching all four turns it into a stamp — and its stub runs the full
height, because a perforation that stops short reads as a panel rather than a
tear line. Two details the hero has no room for: a nick bitten out of each end of
the perforation, which is `favicon.svg`'s own geometry — a punched circle at each
end of its dashed line — and the serial repeated on the stub, since the point of
a stub is that both halves carry the number once it's torn. The card is also
deliberately static — no live counts — so nothing on it can go stale between
scrapes; the stat strip carries the three verbs instead.

### Other notes

The cover `<a>` carries `tabindex="-1"` and `aria-hidden="true"` because the
title link immediately below it points at the same URL — without that, keyboard
and screen-reader users hit three links per card, two of them identical.
