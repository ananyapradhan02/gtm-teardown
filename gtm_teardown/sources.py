"""Reading copy in (text, file, URL, CSV) and small output helpers."""

from __future__ import annotations

import csv
import html
import re
import sys
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple
from urllib.request import Request, urlopen

_TAG_RX = re.compile(r"<(script|style|noscript)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_HTML_RX = re.compile(r"<[^>]+>")
_WS_RX = re.compile(r"[ \t\r\f\v]+")


def html_to_text(raw: str) -> str:
    raw = _TAG_RX.sub(" ", raw)
    raw = re.sub(r"</(p|div|li|h[1-6]|tr|br|section|article)>", "\n", raw, flags=re.IGNORECASE)
    text = html.unescape(_HTML_RX.sub(" ", raw))
    text = _WS_RX.sub(" ", text)
    return re.sub(r"\n\s*\n+", "\n", text).strip()


def fetch_url(url: str, timeout: int = 20) -> str:
    req = Request(url, headers={"User-Agent": "gtm-teardown/0.12 (+https://github.com/ananyapradhan02/gtm-teardown)"})
    with urlopen(req, timeout=timeout) as resp:  # noqa: S310 - user-supplied URL by design
        return html_to_text(resp.read().decode("utf-8", errors="replace"))


def read_copy(text: str | None = None, file: str | None = None, url: str | None = None) -> str:
    """Exactly one of text/file/url must be given."""
    given = [x for x in (text, file, url) if x]
    if len(given) != 1:
        raise ValueError("provide exactly one of --text, --file or --url")
    if text:
        return text
    if file:
        return Path(file).read_text(encoding="utf-8", errors="replace")
    return fetch_url(url)  # type: ignore[arg-type]


def read_companies_csv(path: str) -> List[Tuple[str, str]]:
    """CSV with a ``company`` column and a ``copy`` (or ``text``) column.
    Rows with an empty copy are skipped with a warning."""
    rows: List[Tuple[str, str]] = []
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames:
            raise ValueError(f"{path}: empty CSV")
        fields = {f.strip().lower(): f for f in reader.fieldnames}
        if "company" not in fields:
            raise ValueError(f"{path}: needs a 'company' column (has {reader.fieldnames})")
        copy_col = fields.get("copy") or fields.get("text")
        if not copy_col:
            raise ValueError(f"{path}: needs a 'copy' (or 'text') column")
        for row in reader:
            company = (row.get(fields["company"]) or "").strip()
            copy = (row.get(copy_col) or "").strip()
            if not company:
                continue
            if not copy:
                print(f"[gtm-teardown] skipping {company}: empty copy", file=sys.stderr)
                continue
            rows.append((company, copy))
    return rows


def find_company(rows: Sequence[Tuple[str, str]], name: str) -> Tuple[str, str]:
    for company, copy in rows:
        if company.lower() == name.lower():
            return company, copy
    known = ", ".join(c for c, _ in rows)
    raise KeyError(f"{name!r} not in CSV (known: {known})")


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "company"


def md_table(headers: Sequence[str], rows: Iterable[Sequence[object]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(str(c).replace("|", "\\|") for c in row) + " |")
    return "\n".join(lines)


def text_table(headers: Sequence[str], rows: Sequence[Sequence[object]]) -> str:
    rows = [[str(c) for c in r] for r in rows]
    widths = [max(len(h), *(len(r[i]) for r in rows)) if rows else len(h) for i, h in enumerate(headers)]
    fmt = "  ".join("{:<" + str(w) + "}" for w in widths)
    out = [fmt.format(*headers), fmt.format(*["-" * w for w in widths])]
    out += [fmt.format(*r) for r in rows]
    return "\n".join(out)
