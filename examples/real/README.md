# Real pages

`companies.csv` is a watchlist of six agentic-AI companies by **URL only** — no copy is stored here. The tool fetches each page live when a CSV row has a `url` and no `copy`:

```bash
gtm-teardown batch  --csv examples/real/companies.csv --out reports/
gtm-teardown report --csv examples/real/companies.csv
gtm-teardown watch  --csv examples/real/companies.csv        # run weekly; reports only real positioning moves
```

The Markdown files alongside are what the tool produced from these pages on **2026-09-26** (`reports/` per company, `landscape.md`, `ranking.md`, `compare-fin-vs-decagon.md`, `essay-draft.md`). Evidence lines quote the clause each classification rests on, so every read can be checked against the page. Pages change; re-run to see what moved.

What the first run against real pages found, and fixed (all locked in `tests/test_regressions.py` as Day 13):

- Price patterns written with `\b` before `$` never matched after a space — `$185/mo` and `$40/user` were dead code.
- Usage pricing is phrased as *credits* and *pay only when* on real pages, not "usage-based".
- Cost claims are nominalised: "65% reduction in costs", "Decrease costs per lead", "support costs go down".
- "without supervision" was negating an autonomy claim five words later.
- A clause listing five integration names counted five times; a clause is now one hit.
- A three-way tie at 1 of 6 was reported as "usage-based leads".
- Ada's `/pricing/` URL redirects to a demo form. No public pricing page is itself a sales-led finding; the fetcher now says so.
