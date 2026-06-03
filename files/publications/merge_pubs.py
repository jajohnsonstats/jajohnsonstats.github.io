import yaml
from pathlib import Path

AUTO_FILE = Path("files/publications/publications_auto.yml")
MANUAL_FILE = Path("files/publications/publications_manual.yml")
OUTPUT_FILE = Path("files/publications/publications.yml")

## Function to Load Data --------------------------------------------
def load_yaml(path):
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or []

## Function to Merge Records ----------------------------------------
def merge_records(auto_list, manual_list):
    ## Index manual entries by DOI (preferred) or title
    manual_index = {}
    for m in manual_list:
        key = m.get("doi") or m.get("title")
        if key:
            manual_index[key] = m

    merged = []

    for a in auto_list:
        key = a.get("doi") or a.get("title")
        if key in manual_index:
            ## Merge: manual fields override auto fields
            merged.append({**a, **manual_index[key]})
        else:
            merged.append(a)

    ## Add manual-only entries (e.g., unpublished work)
    for key, m in manual_index.items():
        if not any((rec.get("doi") or rec.get("title")) == key for rec in merged):
            merged.append(m)

    return merged

## Function to put it all together ----------------------------------
def main():
    auto = load_yaml(AUTO_FILE)
    manual = load_yaml(MANUAL_FILE)
    merged = merge_records(auto, manual)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        yaml.dump(merged, f, sort_keys=False, allow_unicode=True)

if __name__ == "__main__":
    main()
