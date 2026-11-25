"""Temporary check: can GitHub read fundsforNGOs article pages (robots.txt allowing), and what do they contain?"""
import json, re, urllib.request, urllib.robotparser

UA = "Mozilla/5.0 (compatible; heartfulness-funding-tracker; +https://github.com/martinbuess/heartfulness-funding-tracker)"
PAGES = [
    "https://www2.fundsforngos.org/articles-searching-grants-and-donors/5-grantmakers-for-indian-ngos-working-with-women-farmers-and-producer-collectives/",
    "https://www2.fundsforngos.org/individuals/global-eba-fund-medium-size-grants-call-for-proposals/",
    "https://www2.fundsforngos.org/innovation/open-call-for-wisser-and-family-innovation-challenge-3-0-india/",
]
out = {}
def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.status, r.read().decode("utf-8", "replace")
try:
    status, robots = get("https://www2.fundsforngos.org/robots.txt")
    out["robots"] = robots[:4000]
except Exception as e:
    out["robots"] = f"ERROR {e}"
rp = urllib.robotparser.RobotFileParser()
rp.parse(out["robots"].splitlines() if not out["robots"].startswith("ERROR") else [])
for url in PAGES:
    row = {"robots_allowed": rp.can_fetch(UA, url)}
    try:
        status, page = get(url)
        text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"(?is)<(script|style).*?</\1>", " ", page)))
        i = text.find("at a Glance")
        row.update(status=status, bytes=len(page), glance=text[i:i + 900] if i >= 0 else "",
                   start=text[:300], links=[h for h in re.findall(r'href="(https?://[^"]+)"', page)
                                            if "fundsforngos" not in h][:40])
    except Exception as e:
        row["error"] = str(e)[:200]
    out[url] = row
json.dump(out, open("probe/probe_results.json", "w"), indent=1)
