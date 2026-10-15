"""Second check: robots.txt rules, permitted feeds, and the EU search filters."""
import json, urllib.request, urllib.robotparser

UA = "Mozilla/5.0 (compatible; heartfulness-funding-tracker; +https://github.com/martinbuess/heartfulness-funding-tracker)"
out = {}

def get(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.status, r.headers.get("Content-Type", ""), r.read()

for host in ["https://www2.fundsforngos.org", "https://www.hclfoundation.org", "https://terravivagrants.org",
             "https://www.terravivagrants.org", "https://www.indiawaterportal.org"]:
    try:
        out[host + "/robots.txt"] = get(host + "/robots.txt")[2].decode("utf-8", "replace")[:3000]
    except Exception as e:
        out[host + "/robots.txt"] = f"ERROR {e}"

checks = {}
for host, paths in {"https://www2.fundsforngos.org": ["/feed/", "/category/latest-funds-for-ngos/feed/",
                     "/tag/india/feed/", "/category/environment-2/feed/", "/wp-json/wp/v2/posts", "/?s=india&feed=rss2",
                     "/latest-funds-for-ngos/"],
                    "https://www.hclfoundation.org": ["/hcltech-grant", "/"],
                    "https://www.terravivagrants.org": ["/feed/", "/wp-json/wp/v2/posts"]}.items():
    rp = urllib.robotparser.RobotFileParser(host + "/robots.txt")
    rp.parse(out[host + "/robots.txt"].splitlines() if not out[host + "/robots.txt"].startswith("ERROR") else [])
    for p in paths:
        row = {"robots_allowed": rp.can_fetch(UA, host + p)}
        try:
            status, ctype, body = get(host + p)
            row.update(status=status, type=ctype, bytes=len(body),
                       items=body.count(b"<item>"), start=" ".join(body[:300].decode("utf-8", "replace").split()))
        except Exception as e:
            row["error"] = str(e)[:200]
        checks[host + p] = row
out["checks"] = checks

# EU search: open (31094501) and forthcoming (31094502) calls; inspect fields.
SEDIA = "https://api.tech.ec.europa.eu/search-api/prod/rest/search?apiKey=SEDIA&text={text}&pageSize=20&pageNumber=1"
def sedia(text, query):
    boundary = "----fbhprobe"
    parts = ""
    for name, value in (("query", query), ("languages", ["en"])):
        parts += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"; filename=\"blob\"\r\n"
                  f"Content-Type: application/json\r\n\r\n{json.dumps(value)}\r\n")
    body = (parts + f"--{boundary}--\r\n").encode()
    status, ctype, data = get(SEDIA.format(text=text), data=body,
                              headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    return json.loads(data)

q = {"bool": {"must": [{"terms": {"type": ["1", "2", "8"]}}, {"terms": {"status": ["31094501", "31094502"]}}]}}
res = {}
for text in ["***", "restoration", "biodiversity India", "agroforestry"]:
    try:
        j = sedia(text, q)
        res[text] = {"total": j.get("totalResults"), "sample": [
            {k: r.get("metadata", {}).get(k) for k in ("identifier", "title", "callTitle", "status", "type", "deadlineDate",
                                                     "startDate", "frameworkProgramme", "budgetOverview", "links")}
            | {"url": r.get("url"), "summary": (r.get("summary") or "")[:200]}
            for r in j.get("results", [])[:4]]}
    except Exception as e:
        res[text] = {"error": str(e)[:300]}
out["sedia"] = res
json.dump(out, open("probe_results.json", "w"), indent=1, default=str)
