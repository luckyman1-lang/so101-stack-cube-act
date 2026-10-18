import json, urllib.request
d = json.load(urllib.request.urlopen("https://pypi.org/pypi/rerun-sdk/json", timeout=60))
rel = d["releases"]
def key(s):
    import re
    return [int(x) for x in re.findall(r"\d+", s)[:3]]
for v in sorted(rel, key=key):
    if v.startswith(("0.20", "0.21", "0.22", "0.23", "0.24")):
        files = [f["filename"] for f in rel[v]]
        wins = [f for f in files if "win_amd64" in f]
        print(f"{v:<10} 共{len(files)}个文件, win_amd64={len(wins)}  {wins[:2]}")
