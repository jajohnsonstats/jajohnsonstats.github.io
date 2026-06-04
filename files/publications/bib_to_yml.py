import bibtexparser
import yaml
import requests
import re
from urllib.parse import quote

INPUT_BIB = "files/CV/publications.bib"
OUTPUT_YML = "files/publications/publications_auto.yml"

ORCID_SEARCH_URL = "https://pub.orcid.org/v3.0/expanded-search/?q=doi:"
ARXIV_API_URL = "http://export.arxiv.org/api/query?search_query=id:"

HEADERS = {
    "Accept": "application/json"
}

## Cleaning Functions -----------------------------------------------
def clean_title(title):
    """Remove BibTeX braces and LaTeX commands from titles."""
    title = re.sub(r"\\[a-zA-Z]+\{([^}]*)\}", r"\1", title)
    return title.replace("{", "").replace("}", "").strip()

def clean_authors(authors_raw):
    ## Remove LaTeX commands like \me{...}
    authors_raw = re.sub(r"\\[a-zA-Z]+\{([^}]*)\}", r"\1", authors_raw)
    authors_raw = authors_raw.replace("{", "").replace("}", "")

    ## Normalize Author Names
    authors = []
    for name in authors_raw.split(" and "):
        name = name.strip()

        ## Case 1: "Last, First"
        if "," in name:
            last, first = [part.strip() for part in name.split(",", 1)]
            authors.append(f"{first} {last}")

        ## Case 2: "First Last"
        else:
            authors.append(name)

    return ", ".join(authors)


## Lookup Functions -------------------------------------------------
def lookup_orcid_metadata(doi):
    """Query ORCID for metadata using DOI."""
    try:
        url = ORCID_SEARCH_URL + quote(doi)
        response = requests.get(url, headers=HEADERS, timeout=10)

        if response.status_code != 200:
            return {}

        data = response.json()
        if "expanded-result" not in data or len(data["expanded-result"]) == 0:
            return {}

        entry = data["expanded-result"][0]
        metadata = {}

        ## Abstract / description
        metadata["abstract"] = (
            entry.get("work-summary", [{}])[0].get("short-description", "")
        )

        ## Journal title
        metadata["journal"] = entry.get("journal-title", "")

        ## Publisher
        metadata["publisher"] = entry.get("publisher", "")

        ## Work type
        metadata["type"] = entry.get("type", "")

        ## Publication date
        pub_date = entry.get("publication-date", {})
        if pub_date:
            year = pub_date.get("year", {}).get("value", "")
            month = pub_date.get("month", {}).get("value", "")
            day = pub_date.get("day", {}).get("value", "")
            metadata["published"] = "-".join(
                [str(x) for x in [year, month, day] if x]
            )

        ## Keywords
        keywords = entry.get("keywords", {}).get("keyword", [])
        metadata["keywords"] = [kw.get("content", "") for kw in keywords]

        ## Subjects
        subjects = entry.get("subject", [])
        metadata["subjects"] = [s.get("content", "") for s in subjects]

        ## External IDs (CrossRef, PubMed, Scopus, arXiv)
        ext_ids = entry.get("external-id", [])
        metadata["external_ids"] = {
            e.get("external-id-type", ""): e.get("external-id-value", "")
            for e in ext_ids
        }

        ## ORCID contributors
        metadata["orcid_authors"] = [
            {
                "name": a.get("credit-name", ""),
                "orcid": a.get("orcid-id", "")
            }
            for a in entry.get("contributors", [])
        ]

        ## Remove empty fields
        return {k: v for k, v in metadata.items() if v}

    except Exception:
        return {}


def lookup_arxiv_metadata(arxiv_id):
    """Query arXiv for metadata using arXiv ID."""
    try:
        url = ARXIV_API_URL + quote(arxiv_id)
        response = requests.get(url, timeout=10)

        if response.status_code != 200:
            return {}

        text = response.text

        ## Extract title
        title_match = re.search(r"<title>(.*?)</title>", text, re.DOTALL)
        title = title_match.group(1).strip() if title_match else ""

        ## Extract abstract
        abstract_match = re.search(r"<summary>(.*?)</summary>", text, re.DOTALL)
        abstract = abstract_match.group(1).strip() if abstract_match else ""

        ## Extract published date
        date_match = re.search(r"<published>(.*?)</published>", text)
        published = date_match.group(1).strip() if date_match else ""

        return {
            "arxiv_title": title,
            "abstract": abstract,
            "published": published,
            "type": "preprint"
        }

    except Exception:
        return {}


## Conversion Function ----------------------------------------------
def bib_to_yaml():
    with open(INPUT_BIB, "r", encoding="utf-8") as bibfile:
        bib_database = bibtexparser.load(bibfile)

    entries = []

    for entry in bib_database.entries:
        doi = entry.get("doi", "").strip()
        arxiv_id = entry.get("eprint", "").strip() if entry.get("archiveprefix", "").lower() == "arxiv" else ""

        ## Base metadata from .bib
        item = {
            "title": clean_title(entry.get("title", "")),
            "authors": clean_authors(entry.get("author", "")),
            "year": entry.get("year", ""),
            "journal": entry.get("journal", entry.get("booktitle", "")),
            "doi": doi,
            "abstract": entry.get("abstract", ""),
            "url": entry.get("url", f"https://doi.org/{doi}") if doi else "",
            "path": entry.get("path", "")
        }

        ## ORCID enrichment
        if doi:
            orcid_data = lookup_orcid_metadata(doi)
            item.update({k: v for k, v in orcid_data.items() if v})

        ## arXiv enrichment
        if arxiv_id:
            arxiv_data = lookup_arxiv_metadata(arxiv_id)
            item.update({k: v for k, v in arxiv_data.items() if v})

        ## Remove empty fields
        item = {k: v for k, v in item.items() if v}

        entries.append(item)

    ## Write YAML
    with open(OUTPUT_YML, "w", encoding="utf-8") as ymlfile:
        yaml.dump(entries, ymlfile, sort_keys=False, allow_unicode=True)

    print(f"Generated {OUTPUT_YML} with {len(entries)} entries.")


if __name__ == "__main__":
    bib_to_yaml()
