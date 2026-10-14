"""
bib_to_yml.py: build the website's publication list from the CV's .bib file
==============================================================================

    files/CV/publications.bib  -->  files/publications/publications.yml

Runs automatically before every render (see `pre-render` in _quarto.yml).
You can also run it by hand from the project root:

    python files/publications/bib_to_yml.py

The .bib file is the ONLY place publication data lives. To add a paper,
add its entry to publications.bib (in the CV repo) and re-render.

Requires: bibtexparser (version 1.x) and PyYAML
    pip install "bibtexparser<2" pyyaml

------------------------------------------------------------------------------
Fields read from each .bib entry
------------------------------------------------------------------------------
Standard BibTeX:
    author, title, journal (or booktitle), volume, number, pages,
    year, month, day, doi, url, abstract,
    eprint + archiveprefix = {arXiv}   ->  "Preprint" button to arXiv

Website-only (BibTeX/Biber ignore these, so the CV is unaffected):
    code, slides, poster, data, supplement   ->  buttons
    preprint                                 ->  "Preprint" button for a
                                                 non-arXiv preprint URL
    award                                    ->  award line
    status = {preprint | published}          ->  override automatic grouping

Bolding my name: an author is bolded if EITHER
    - the entry has author+an = {N=highlight} for that position, OR
    - the name matches one of MY_NAMES below, OR
    - the name is wrapped in the old \\me{...} macro.

------------------------------------------------------------------------------
Output (one YAML item per paper; read by pub-listing.ejs)
------------------------------------------------------------------------------
    key, title, authors: [{name, me}], venue, volume, issue, pages,
    pubdate ("YYYY", "YYYY-MM", or "YYYY-MM-DD"), status,
    paper, preprint, code, slides, poster, data, supplement, award, abstract

Note: the date is written as `pubdate`, not `date`, because Quarto treats a
listing item's `date` field specially and would try to reformat it.
"""

import re
import sys
from pathlib import Path

import bibtexparser
import yaml
from bibtexparser.bparser import BibTexParser


# =============================================================================
# SETTINGS
# =============================================================================

INPUT_BIB = Path("files/CV/publications.bib")
OUTPUT_YML = Path("files/publications/publications.yml")

# Spellings of my name to bold, in either "Last, First" or "First Last" form.
# Compared after cleanup, so braces and \me{} don't matter.
MY_NAMES = {"Johnson, Jacob A.", "Jacob A. Johnson"}

# Website-only .bib fields copied straight through to the YAML.
PASSTHROUGH_FIELDS = ["code", "slides", "poster", "data", "supplement", "award"]

# If True, a .bib entry that fails to parse stops the render with an error.
# If False (default), the script prints a warning and continues without it.
STRICT = False


# =============================================================================
# LATEX CLEANUP
# Converts the small amount of LaTeX that shows up in titles, names, and
# abstracts into plain text/HTML. Math ($...$) is kept for MathJax.
# =============================================================================

# Simple replacements, applied in order.
LATEX_REPLACEMENTS = [
    (r"\&", "&"),
    (r"\%", "%"),
    (r"\_", "_"),
    (r"\#", "#"),
    ("---", "\u2014"),   # em dash
    ("--", "\u2013"),    # en dash
    ("~", "\u00a0"),     # non-breaking space
    ("``", "\u201c"),    # opening double quote
    ("''", "\u201d"),    # closing double quote
]


def split_math(text):
    """Split text into (is_math, chunk) pieces so math is left untouched."""
    parts = re.split(r"(\$[^$]+\$)", text)
    return [(p.startswith("$") and p.endswith("$") and len(p) > 1, p) for p in parts if p]


def clean_latex(text):
    """Strip LaTeX markup from non-math text; convert $...$ to \\(...\\) for MathJax."""
    out = []
    for is_math, chunk in split_math(text or ""):
        if is_math:
            # MathJax on the site recognizes \( ... \) for inline math.
            out.append("\\(" + chunk[1:-1] + "\\)")
            continue
        # Unwrap simple commands like \emph{x}, \textit{x}, \me{x} -> x
        chunk = re.sub(r"\\[a-zA-Z]+\{([^{}]*)\}", r"\1", chunk)
        # Remove protective braces, e.g. {Gaussian} -> Gaussian
        chunk = chunk.replace("{", "").replace("}", "")
        for old, new in LATEX_REPLACEMENTS:
            chunk = chunk.replace(old, new)
        out.append(chunk)
    # Collapse runs of whitespace (BibTeX entries are often line-wrapped)
    return re.sub(r"\s+", " ", "".join(out)).strip()


# =============================================================================
# AUTHORS
# =============================================================================

def parse_highlights(annotation):
    """
    Read biblatex name annotations, e.g. "1=highlight" or "1=highlight; 3=highlight".
    Returns the set of 1-based author positions marked 'highlight'.
    """
    positions = set()
    for item in (annotation or "").split(";"):
        if "=" not in item:
            continue
        pos, labels = item.split("=", 1)
        if pos.strip().isdigit() and "highlight" in [l.strip() for l in labels.split(",")]:
            positions.add(int(pos.strip()))
    return positions


def display_name(name):
    """Turn a BibTeX name into "First Last" order."""
    parts = [p.strip() for p in name.split(",")]
    if len(parts) == 3:          # "Last, Jr., First"
        last, suffix, first = parts
        return f"{first} {last} {suffix}"
    if len(parts) == 2:          # "Last, First"
        last, first = parts
        return f"{first} {last}"
    return name                  # already "First Last"


def parse_authors(raw, annotation):
    """Return a list of {name, me} dicts in author order."""
    highlights = parse_highlights(annotation)
    authors = []
    for i, original in enumerate(re.split(r"\s+and\s+", raw or ""), start=1):
        if not original.strip():
            continue
        used_me_macro = "\\me{" in original
        cleaned = clean_latex(original)
        is_me = (
            i in highlights
            or used_me_macro
            or cleaned in MY_NAMES
            or display_name(cleaned) in MY_NAMES
        )
        authors.append({"name": display_name(cleaned), "me": is_me})
    return authors


# =============================================================================
# DATES, STATUS, LINKS
# =============================================================================

MONTH_WORDS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def parse_month(value):
    """Accept 6, "6", "06", "jun", "June" -> 6. Returns None if missing/unknown."""
    value = str(value or "").strip().lower()
    if value.isdigit():
        return int(value) if 1 <= int(value) <= 12 else None
    return MONTH_WORDS.get(value[:3])


def build_pubdate(entry):
    """Return "YYYY", "YYYY-MM", or "YYYY-MM-DD" (sortable as text)."""
    year = str(entry.get("year", "")).strip()
    if not year.isdigit():
        return ""
    month = parse_month(entry.get("month"))
    if not month:
        return year
    day = str(entry.get("day", "")).strip()
    if day.isdigit():
        return f"{year}-{month:02d}-{int(day):02d}"
    return f"{year}-{month:02d}"


def arxiv_id(entry):
    """arXiv ID if the entry has eprint + archiveprefix = arXiv, else ""."""
    prefix = entry.get("archiveprefix", entry.get("eprinttype", "")).strip().lower()
    return entry.get("eprint", "").strip() if prefix == "arxiv" else ""


def build_status(entry):
    """
    'published' for journal articles and conference papers, 'preprint'
    otherwise. Override with status = {preprint} or {published} in the .bib.
    """
    explicit = entry.get("status", "").strip().lower()
    if explicit in {"preprint", "published"}:
        return explicit
    if entry.get("ENTRYTYPE") in {"article", "inproceedings", "incollection"} and (
        entry.get("journal") or entry.get("booktitle")
    ):
        return "published"
    return "preprint"


def is_arxiv_link(value):
    """True for arXiv URLs and arXiv's own DOIs (10.48550/arXiv....)."""
    value = value.lower()
    return "arxiv.org" in value or "10.48550/" in value


def paper_link(entry):
    """
    Link for the "Paper" button: the journal version (DOI, else url).
    arXiv links are skipped here because they belong on the "Preprint"
    button; arXiv's own BibTeX export includes an arXiv url (and sometimes
    an arXiv DOI), which would otherwise create a duplicate button.
    """
    for value in (entry.get("doi", "").strip(), entry.get("url", "").strip()):
        if not value or is_arxiv_link(value):
            continue
        if value.startswith("http"):
            return value
        return f"https://doi.org/{value}"
    return ""


def preprint_link(entry):
    aid = arxiv_id(entry)
    if aid:
        return f"https://arxiv.org/abs/{aid}"
    return entry.get("preprint", "").strip()


# =============================================================================
# PARSING (with a check for silently dropped entries)
# =============================================================================

# Entry types that aren't publications and shouldn't be counted.
NON_ENTRIES = {"comment", "string", "preamble"}


def keys_in_file(text):
    """Find every entry key by scanning the raw text (independent of the parser)."""
    found = re.findall(r"^\s*@(\w+)\s*[{(]\s*([^,\s]+)\s*,", text, flags=re.MULTILINE)
    return [key for kind, key in found if kind.lower() not in NON_ENTRIES]


def load_bib(path):
    text = path.read_text(encoding="utf-8")
    parser = BibTexParser(common_strings=True)   # understands month macros like `jun`
    parser.ignore_nonstandard_types = False
    database = bibtexparser.loads(text, parser=parser)

    # bibtexparser skips malformed entries without complaint, so compare its
    # result against a plain-text scan and report anything that went missing.
    parsed = {e["ID"] for e in database.entries}
    missing = [k for k in keys_in_file(text) if k not in parsed]
    if missing:
        msg = (
            f"\n*** bib_to_yml.py WARNING: {len(missing)} .bib entr"
            f"{'y' if len(missing) == 1 else 'ies'} could not be read and "
            f"will NOT appear on the website: {', '.join(missing)}\n"
            "*** Usually a missing comma, brace, or quote inside that entry.\n"
        )
        if STRICT:
            sys.exit(msg)
        print(msg, file=sys.stderr)

    return database.entries


# =============================================================================
# MAIN
# =============================================================================

def entry_to_item(entry):
    item = {
        "key": entry.get("ID", ""),
        "title": clean_latex(entry.get("title", "")),
        "authors": parse_authors(entry.get("author", ""), entry.get("author+an", "")),
        "venue": clean_latex(entry.get("journal", entry.get("booktitle", ""))),
        "volume": entry.get("volume", "").strip(),
        "issue": entry.get("number", "").strip(),
        "pages": clean_latex(entry.get("pages", "")),
        "pubdate": build_pubdate(entry),
        "status": build_status(entry),
        "arxiv": arxiv_id(entry),
        "paper": paper_link(entry),
        "preprint": preprint_link(entry),
        "abstract": clean_latex(entry.get("abstract", "")),
    }
    for field in PASSTHROUGH_FIELDS:
        item[field] = clean_latex(entry.get(field, "")) if field == "award" else entry.get(field, "").strip()

    # Drop empty fields so the YAML stays readable (the template checks for them).
    return {k: v for k, v in item.items() if v not in ("", None, [])}


def main():
    if not INPUT_BIB.exists():
        sys.exit(
            f"bib_to_yml.py: {INPUT_BIB} not found. Run this from the project root, "
            "and check that the CV submodule is checked out."
        )

    items = [entry_to_item(e) for e in load_bib(INPUT_BIB)]

    # Newest first (the template also sorts; this just keeps the YAML tidy).
    items.sort(key=lambda it: it.get("pubdate", ""), reverse=True)

    header = (
        "# GENERATED FILE: do not edit by hand.\n"
        f"# Built from {INPUT_BIB} by files/publications/bib_to_yml.py.\n"
        "# Edit the .bib instead; this file is rewritten on every render.\n\n"
    )
    OUTPUT_YML.write_text(
        header + yaml.safe_dump(items, sort_keys=False, allow_unicode=True, width=1000),
        encoding="utf-8",
    )
    print(f"bib_to_yml.py: wrote {len(items)} publication(s) to {OUTPUT_YML}")


if __name__ == "__main__":
    main()
