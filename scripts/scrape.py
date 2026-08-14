#!/usr/bin/env python3
"""
Builds giveaways.json for the discovery board.

Goodreads' giveaway browse page is a Next.js app backed by AWS AppSync. This
hits that GraphQL endpoint directly — no HTML parsing, no login, no cookies.

Verified against the live API:
  - endpoint    kxbwmqov6jgg3daaamb744ycu4.appsync-api.us-east-1.amazonaws.com
  - auth        public x-api-key baked into the client bundle (no session needed)
  - page size   server caps at 15 regardless of what you ask for
  - pagination  opaque cursor: pageInfo.nextPageToken -> pagination.after
  - total       1,364 open print giveaways, so ~91 requests per full run

Twice a day is plenty. Sequential, with a delay between pages.

Writes public/giveaways.json (what the page reads) and appends one
{ts, slug, entries} line per giveaway to data/snapshots/YYYY-MM-DD.jsonl.
Dated snapshot files keep git from re-storing an ever-growing blob every run.
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

import requests

ENDPOINT = "https://kxbwmqov6jgg3daaamb744ycu4.appsync-api.us-east-1.amazonaws.com/graphql"

# Public client key lifted from the page bundle. It will rotate on some future
# Goodreads deploy; discover_api_key() below re-finds it when that happens.
API_KEY = "da2-xpgsdydkbregjhpr6ejzqdhuwy"

PAGE_SIZE = 15          # server-enforced ceiling
DELAY = 1.0
MAX_PAGES = 200
FORMAT = "PRINT"        # enum. KINDLE is likely the ebook value but is untested.
SORT = "ENDING_SOON"    # also seen in the UI: FEATURED, RECENT, POPULAR

# A crawl that dies partway through must not overwrite a good giveaways.json
# with a truncated list. Anything under this share of the API-reported total
# aborts without writing.
MIN_COMPLETENESS = 0.90

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

QUERY = """
query GetGiveaways($input: GetGiveawaysInput!, $pagination: PaginationInput) {
  getGiveaways(getGiveawaysInput: $input, pagination: $pagination) {
    totalCount
    pageInfo { hasNextPage nextPageToken }
    edges {
      node {
        legacyId
        webUrl
        details {
          numCopiesAvailable
          numEntrants
          format
          genres { name }
          book {
            title
            imageUrl
            primaryContributorEdge { node { name webUrl } role }
          }
        }
        metadata {
          startDate
          endDate
          countries { countryCode }
        }
      }
    }
  }
}
"""


def variables(after, limit):
    return {
        "input": {"format": FORMAT, "genre": "all", "sort": SORT},
        "pagination": {"after": after, "limit": limit},
    }


def probe(session, key):
    r = session.post(
        ENDPOINT,
        headers={"x-api-key": key},
        json={"query": QUERY, "variables": variables(None, 1)},
        timeout=20,
    )
    return r.status_code == 200 and not r.json().get("errors")


def discover_api_key(session):
    """Re-find the public key from the page bundle if the hardcoded one 401s."""
    html = session.get("https://www.goodreads.com/giveaway", timeout=20).text
    for src in re.findall(r'src="(/_next/static/[^"]+\.js)"', html):
        js = session.get("https://www.goodreads.com" + src, timeout=20).text
        for key in re.findall(r"da2-[a-z0-9]{26}", js):
            if probe(session, key):
                return key
    raise RuntimeError("could not find a working API key in the page bundle")


def fetch_page(session, key, after):
    r = session.post(
        ENDPOINT,
        headers={"x-api-key": key},
        json={"query": QUERY, "variables": variables(after, PAGE_SIZE)},
        timeout=30,
    )
    r.raise_for_status()
    body = r.json()
    if body.get("errors"):
        raise RuntimeError(body["errors"][0].get("message", "graphql error"))
    return body["data"]["getGiveaways"]


def flatten(node):
    d = node["details"]
    book = d["book"]
    contributor = (book.get("primaryContributorEdge") or {}).get("node") or {}
    return {
        "slug": node["webUrl"].rsplit("/giveaway/show/", 1)[-1],
        "legacyId": node["legacyId"],
        "title": book["title"],
        "author": contributor.get("name", ""),
        "authorUrl": contributor.get("webUrl", ""),
        "cover": book.get("imageUrl"),
        "copies": d["numCopiesAvailable"],
        "entries": d["numEntrants"],
        # The show page (not the login-gated enter_choose_address flow) so
        # logged-out visitors can still see the book before entering.
        "enterUrl": node["webUrl"],
        "genres": [g["name"] for g in d.get("genres") or []],
        "countries": [c["countryCode"] for c in node["metadata"].get("countries") or []],
        "starts": node["metadata"]["startDate"][:10],
        "ends": node["metadata"]["endDate"][:10],
        "endsAt": node["metadata"]["endDate"],
    }


def crawl(max_pages=MAX_PAGES):
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "User-Agent": "giveaway-board/0.2 (personal reading tool)",
    })

    key = API_KEY
    if not probe(session, key):
        print("hardcoded key rejected, rediscovering...", file=sys.stderr)
        key = discover_api_key(session)
        print(f"found working key: {key}", file=sys.stderr)

    seen, after, total = {}, None, None

    for page in range(1, max_pages + 1):
        data = fetch_page(session, key, after)
        total = data["totalCount"]

        for edge in data["edges"]:
            row = flatten(edge["node"])
            seen[row["slug"]] = row

        print(f"page {page:>3}  {len(seen):>5} / {total}")

        if not data["pageInfo"]["hasNextPage"]:
            break
        after = data["pageInfo"]["nextPageToken"]
        time.sleep(DELAY)

    return list(seen.values()), total


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=os.path.join(ROOT, "public", "giveaways.json"),
                    help="path to write giveaways.json")
    ap.add_argument("--snapshots", default=os.path.join(ROOT, "data", "snapshots"),
                    help="directory for dated snapshot files ('' to skip)")
    ap.add_argument("--max-pages", type=int, default=MAX_PAGES,
                    help="stop after this many pages (for testing)")
    args = ap.parse_args()

    giveaways, total = crawl(args.max_pages)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    # Guard: never replace a good file with a partial crawl.
    if total and len(giveaways) < total * MIN_COMPLETENESS:
        print(f"aborting: only {len(giveaways)} of {total} rows collected "
              f"(<{MIN_COMPLETENESS:.0%}); leaving {args.out} untouched",
              file=sys.stderr)
        return 1

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"updated": now, "total": total, "giveaways": giveaways},
                  f, ensure_ascii=False, separators=(",", ":"))
    print(f"wrote {len(giveaways)} giveaways (API reported {total}) -> {args.out}")

    # Entry-velocity history. Can't be backfilled, so it's on by default.
    # Not read by the page; kept for a future "filling up fast" signal.
    if args.snapshots:
        os.makedirs(args.snapshots, exist_ok=True)
        path = os.path.join(args.snapshots, now[:10] + ".jsonl")
        with open(path, "a", encoding="utf-8") as f:
            for g in giveaways:
                f.write(json.dumps({"ts": now, "slug": g["slug"], "entries": g["entries"]}) + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
