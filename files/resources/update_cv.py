"""
update_cv.py: copy the latest CV files from GitHub into this website
=====================================================================

Downloads the files listed in FILES from the CV repository on GitHub
(github.com/jajohnsonstats/CV) into files/CV/ before every render.
Runs automatically as a `pre-render` step in _quarto.yml, or by hand
from the project root:

    python files/resources/update_cv.py

Workflow: edit and compile your CV in its own repo, commit, and push.
The next website render picks up the pushed version. (GitHub can take
a few minutes to serve a newly pushed file, so re-render if you push
and render immediately and still see the old CV.)

Only Python's standard library is used, so it works the same on
Windows, WSL, macOS, and Linux.

If a download fails (offline, GitHub down, typo in a file name), the
existing copy in files/CV/ is kept and a warning is printed, so the
site still builds. It only stops the render if a file has never been
downloaded at all.
"""

import sys
import urllib.request
from pathlib import Path

# =============================================================================
# SETTINGS
# =============================================================================

# Raw-file address of the CV repo's main branch.
RAW_BASE = "https://raw.githubusercontent.com/jajohnsonstats/CV/main/"

# Files to copy, and a quick check that each download is the real thing
# (GitHub returns a small error page, not your file, if a name is wrong).
FILES = {
    "JacobJohnsonCV.pdf": lambda data: data.startswith(b"%PDF"),
    "publications.bib":   lambda data: b"@" in data,
}

# Where the files go in the website repo.
DEST = Path("files/CV")

TIMEOUT_SECONDS = 20


# =============================================================================
# MAIN
# =============================================================================

def download(name, looks_valid):
    url = RAW_BASE + name
    target = DEST / name
    try:
        request = urllib.request.Request(url, headers={"Cache-Control": "no-cache"})
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            data = response.read()
        if not looks_valid(data):
            raise ValueError("downloaded file doesn't look right")
    except Exception as err:
        if target.exists():
            print(f"update_cv.py WARNING: couldn't download {name} ({err}); "
                  f"keeping the existing copy.", file=sys.stderr)
            return False
        sys.exit(f"update_cv.py ERROR: couldn't download {name} from {url} ({err}), "
                 f"and there is no existing copy in {DEST}/.")

    if target.exists() and target.read_bytes() == data:
        print(f"update_cv.py: {name} is already up to date.")
        return True

    # Write to a temporary file first, then swap it in, so a crash mid-write
    # can't leave a half-written file behind.
    temp = target.with_suffix(target.suffix + ".tmp")
    temp.write_bytes(data)
    temp.replace(target)
    print(f"update_cv.py: updated {name}.")
    return True


def main():
    DEST.mkdir(parents=True, exist_ok=True)
    for name, looks_valid in FILES.items():
        download(name, looks_valid)


if __name__ == "__main__":
    main()
