"""Download portable MinGit (git for Windows, minimal) into .tools/."""
import json
import os
import sys
import urllib.request
import zipfile

DEST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".tools")


def fetch(url: str, timeout: int = 120) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def main() -> int:
    print("Fetching latest git-for-windows release info...")
    meta = json.loads(fetch("https://api.github.com/repos/git-for-windows/git/releases/latest", timeout=60))

    asset = None
    for a in meta.get("assets", []):
        name = a["name"]
        if name.startswith("MinGit-") and name.endswith("-64-bit.zip"):
            asset = a
            break
    if asset is None:
        print("No MinGit 64-bit asset found", file=sys.stderr)
        return 1

    url = asset["browser_download_url"]
    zipname = asset["name"]
    zippath = os.path.join(DEST, zipname)
    os.makedirs(DEST, exist_ok=True)

    if os.path.exists(zippath) and os.path.getsize(zippath) > 1_000_000:
        print(f"Already downloaded: {zippath}")
    else:
        print(f"Downloading {url} ...")
        data = fetch(url, timeout=600)
        with open(zippath, "wb") as f:
            f.write(data)
        print(f"Downloaded {len(data)} bytes")

    extracted = os.path.join(DEST, "mingit")
    if not os.path.isdir(os.path.join(extracted, "cmd", "git.exe")):
        print("Extracting...")
        os.makedirs(extracted, exist_ok=True)
        with zipfile.ZipFile(zippath) as z:
            z.extractall(extracted)

    git_exe = os.path.join(extracted, "cmd", "git.exe")
    print("git.exe:", git_exe)
    return 0


if __name__ == "__main__":
    sys.exit(main())
