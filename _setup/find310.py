import json, re, urllib.request
url = "https://api.github.com/repos/astral-sh/python-build-standalone/releases?per_page=15"
req = urllib.request.Request(url, headers={"User-Agent":"probe"})
rels = json.loads(urllib.request.urlopen(req, timeout=60).read())
pat = re.compile(r"cpython-3\.10\.\d+\+.*x86_64-pc-windows-msvc.*install_only\.tar\.gz$")
print("releases scanned:", len(rels))
for r in rels:
    hits = [a["name"] for a in r["assets"] if pat.search(a["name"])]
    print(f'{r["tag_name"]:>12}  assets={len(r["assets"]):>4}  3.10win={len(hits)}  {hits[:1]}')
