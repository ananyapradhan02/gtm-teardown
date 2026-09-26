# gtm-teardown

**Read how an agentic-AI company sells from the copy it publishes.**

`gtm-teardown` takes a company's public copy (homepage, pricing page, docs intro) and classifies three things every go-to-market decision hangs on:

| dimension | classes |
|---|---|
| **pricing model** | usage-based · tiered SaaS plans · per-seat · custom quote / contact sales |
| **GTM motion** | self-serve (product-led) · sales-led · hybrid |
| **messaging themes** | ROI / cost savings · ease of use · security & compliance · speed / time to value · accuracy & reliability · integrations & ecosystem · autonomy / agents · human in the loop · scale & enterprise readiness |

Then it does the work a growth or product-marketing lead actually does with that: compares two companies, ranks a list against an ICP rubric, watches positioning drift over time, writes the landscape report and essay draft, and drafts the cold-outreach opener — grounded in the company's own words, or not at all.

Built in public by [Ananya Pradhan](https://github.com/ananyapradhan02) — growth lead in agentic AI, writing about **agentic-AI GTM**: how companies that sell autonomous software actually price, position, and go to market. This repo is the tooling under that writing. No dependencies beyond the Python standard library; the optional Claude backend needs `anthropic`.

## Install

```bash
git clone https://github.com/ananyapradhan02/gtm-teardown
cd gtm-teardown
pip install -e ".[dev]"      # add ,llm for the Claude backend
python -m pytest             # 85 tests
```

Python 3.9+. `pip install -e .` gives you the `gtm-teardown` command; `python -m gtm_teardown` works without installing.

## The twelve commands

All examples run against `examples/companies.csv` — five illustrative agentic-AI vendors (fictional, written to sound like real vendor copy). A companies CSV needs a `company` column plus `copy` (pasted text) and/or `url` (fetched live when `copy` is empty). `examples/real/companies.csv` is a URL-only watchlist of six real agentic-AI companies; see [`examples/real/`](examples/real/) for what the tool read off their pages on 2026-09-26.

**One company**

```bash
gtm-teardown run --company "Northwind Agents" --csv examples/companies.csv          # Markdown teardown with evidence
gtm-teardown run --company Acme --url https://example.com/pricing --format json     # from a live page
gtm-teardown run --company Acme --file copy.txt --format table
```

**Many companies**

```bash
gtm-teardown batch  --csv examples/companies.csv --out reports/       # one report per company + summary.json
gtm-teardown compare --csv examples/companies.csv "Northwind Agents" "Lumen Ops"   # head-to-head + positioning wedge
gtm-teardown rank   --csv examples/companies.csv                       # ICP-fit score (swap --rubric examples/rubric-plg.json)
gtm-teardown report --csv examples/companies.csv                       # Markdown landscape write-up + essay seed
gtm-teardown report --csv examples/companies.csv --mode rank           # the ranking as a Markdown table
gtm-teardown essay  --csv examples/companies.csv --out draft.md        # full essay draft, [spans] mark where your argument goes
```

**Over time**

```bash
gtm-teardown snapshot --company "Lumen Ops" --csv examples/companies.csv   # dated, hashed record (identical copy = no-op)
gtm-teardown diff     --company "Lumen Ops"                                 # drift between the two most recent snapshots
gtm-teardown watch    --csv watchlist.csv --min-level high                  # whole watchlist; only significant moves, urgent first
```

**Into the outreach workflow**

```bash
gtm-teardown outreach --company "Northwind Agents" --csv examples/companies.csv --context "I run growth at an agentic-AI company."
gtm-teardown digest   --csv examples/companies.csv --top 5     # Monday triage: rank + drift + openers for the top N
gtm-teardown brief    --company "Harbor Copilot" --csv examples/companies.csv   # one-page call prep for a single account
```

`outreach` exits 2 and says so when the copy gives no usable signal. It never invents a hook: a generic opener is worse than none.

## How the classifier works

It is a heuristic classifier — regexes over the copy — with rules that came from running it on real vendor pages rather than from imagining what vendor pages say:

1. **Clause-scoped matching.** Patterns match inside a clause; clause boundaries are sentence punctuation, `;`, `:`, `--`, em/en dashes and newlines. A negation cue in one sentence never flips a match in the next.
2. **Negation-aware.** "no self-serve plans" is not self-serve evidence. A match is negated only when a cue (`no`, `not`, `never`, `without`, `don't`, `instead of`, ...) appears within five words before it in the same clause.
3. **A bare keyword is not evidence.** "enterprise" alone says nothing about pricing; "enterprise plan" or "tiered plans" does.
4. **Inflections and inserted words are the common case.** "saving 40%", "save *you* 30%", "talk to our sales *team* for pricing" are what pages actually say.
5. **Phrases both motions use are themes, not motion evidence.** "Up and running in minutes" is ease-of-use, whichever way the company sells; counting it as self-serve evidence manufactures false "hybrid" reads.
6. **One clause is one piece of evidence.** A sentence listing five integration names counts once, so long feature lists can't out-rank the theme a page actually leads with.
7. **Real pages phrase things sideways.** Usage pricing shows up as "credits" and "pay only when"; cost claims as "reduction in costs"; a `/pricing` URL that redirects to a demo form is itself a sales-led finding, and the fetcher says so.

Every one of those rules exists because a specific bug was found on a specific day; each has a named regression test in `tests/test_regressions.py`. Evidence snippets are always the clause the match was found in, so any classification can be checked against the page.

`--llm` swaps in a Claude backend (needs `ANTHROPIC_API_KEY` and `pip install anthropic`) that returns the same schema. It auto-falls back to the heuristic backend on any failure and records the reason in the output's `backend` field.

## Rubrics

`rank`, `report --mode rank`, `digest` and `brief` score companies against a JSON rubric of weights (pricing model, GTM motion, top-N themes). The default targets agentic-AI outbound fit — sales-led or hybrid, quote or usage priced, leading with autonomy/ROI/compliance. `examples/rubric-plg.json` shows the opposite bias. Missing keys score zero, so a rubric can be one line.

## Project status

- 12 subcommands, 85 tests, CI on Python 3.9 / 3.11 / 3.12.
- Built daily from 2026-09-14 in short sessions; the day-by-day record — what was added, and which bug was found on real copy that day — is in [`BUILD_LOG.md`](BUILD_LOG.md).
- **Open:** the `--llm` backend is written and its validation/fallback paths are tested, but it has not yet been exercised against a live API key. Treat the heuristic backend as the tested path.
- Day 13 was the first run against real pricing pages (Intercom Fin, Decagon, Ada, Lindy, 11x, Clay): seven bugs found and locked. The illustrative dataset stays for tests; `examples/real/` is the live watchlist.

## License

MIT — see [LICENSE](LICENSE).
