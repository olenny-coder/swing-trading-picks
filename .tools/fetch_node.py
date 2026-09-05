"""Download a portable Node.js (bundles npm + npx) into .tools/ for the frontend."""
import json
import os
import sys
import urllib.request
import zipfile

BASE = "https://nodejs.org/dist"
DEST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".tools")


def fetch(url: str, timeout: int = 120) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def main() -> int:
    print("Fetching release index...")
    idx = json.loads(fetch(f"{BASE}/index.json", timeout=60))

    # Latest v20 LTS (stable with Next.js 14).
    v20 = [v for v in idx if v["version"].startswith("v20.") and v.get("lts")]
    v20.sort(key=lambda v: [int(x) for x in v["version"][1:].split(".")])
    if not v20:
        print("No v20 LTS found", file=sys.stderr)
        return 1
    ver = v20[-1]["version"]
    zipname = f"node-{ver}-win-x64.zip"
    url = f"{BASE}/{ver}/{zipname}"

    os.makedirs(DEST, exist_ok=True)
    zippath = os.path.join(DEST, zipname)

    if os.path.exists(zippath) and os.path.getsize(zippath) > 10_000_000:
        print(f"Already downloaded: {zippath}")
    else:
        print(f"Downloading {url} ...")
        data = fetch(url, timeout=600)
        with open(zippath, "wb") as f:
            f.write(data)
        print(f"Downloaded {len(data)} bytes")

    extracted = os.path.join(DEST, f"node-{ver}-win-x64")
    if not os.path.isdir(extracted):
        print("Extracting...")
        with zipfile.ZipFile(zippath) as z:
            z.extractall(DEST)

    node_exe = os.path.join(extracted, "node.exe")
    npm_cmd = os.path.join(extracted, "npm.cmd")
    print(f"node.exe: {node_exe}")
    print(f"npm.cmd : {npm_cmd}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
