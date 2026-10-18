import os, urllib.request
BASE = "https://files.seeedstudio.com/wiki/robotics/projects/lerobot/so101/cal_{}.jpg"
OUT = r"D:\LeRobot\_setup\calibration_refs"
os.makedirs(OUT, exist_ok=True)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Referer": "https://wiki.seeedstudio.com/cn/lerobot_so100m_new/",
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
}
ok = 0
for code in [f"cal_{p}{i}" for p in "FL" for i in range(1, 7)]:
    path = os.path.join(OUT, f"{code}.jpg")
    if os.path.exists(path) and os.path.getsize(path) > 1000:
        ok += 1; continue
    try:
        req = urllib.request.Request(BASE.format(code), headers=HEADERS)
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
        open(path, "wb").write(data)
        ok += 1
        print(f"  OK {code}  {len(data)/1024:.1f}KB")
    except Exception as e:
        print(f"  FAIL {code}: {type(e).__name__} {e}")
print(f"成功 {ok}/12")
