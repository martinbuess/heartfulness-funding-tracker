"""One-off check of candidate sources: reachable? allowed by robots.txt? what comes back?"""
import json, urllib.request, urllib.robotparser, urllib.parse, urllib.error

UA = "Mozilla/5.0 (compatible; heartfulness-funding-tracker; +https://github.com/martinbuess/heartfulness-funding-tracker)"
SEDIA = "https://api.tech.ec.europa.eu/search-api/prod/rest/search?apiKey=SEDIA&text=***&pageSize=5&pageNumber=1"
SEDIA_QUERY = {"bool": {"must": [{"terms": {"type": ["1", "2", "8"]}}, {"terms": {"status": ["31094501", "31094502"]}}]}}
URLS = [
    "https://www2.fundsforngos.org/wp-json/wp/v2/posts?per_page=2&_fields=id,title",
    "https://terravivagrants.org/wp-json/wp/v2/posts?per_page=3&_fields=id,date,link,title",
    "https://www.terravivagrants.org/feed/",
    "https://www.hclfoundation.org/hcltech-grant",
    "https://www.wiprofoundation.org/upcoming-grants-alert/",
    "https://www.wiprofoundation.org/ecology_programs/community-ecology-program/",
    "https://www.unep.org/gan/node/14",
    "https://sgp.undp.org/",
    "https://www.darwininitiative.org.uk/apply/",
    "https://www.cepf.net/grants/open-calls-for-proposals",
    "https://www.indiawaterportal.org/opportunities",
    "https://www.international-climate-initiative.com/en/find-funding/",
    "https://www.keidanren.net/kncf/fund/project",
    "https://www.welthungerhilfe.org/global-food-system-challenge/your-application",
    "https://www.speciesconservation.org/grants/",
    "https://whitleyaward.org/apply-for-conservation-funding/apply-for-a-whitley-award/",
]
robots = {}

def allowed(url):
    p = urllib.parse.urlsplit(url)
    base = f"{p.scheme}://{p.netloc}"
    if base not in robots:
        rp = urllib.robotparser.RobotFileParser(base + "/robots.txt")
        try:
            req = urllib.request.Request(base + "/robots.txt", headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                rp.parse(r.read().decode("utf-8", "replace").splitlines())
        except urllib.error.HTTPError as e:
            rp.allow_all = e.code >= 400 and e.code not in (401, 403)
            rp.disallow_all = e.code in (401, 403)
        except Exception as e:
            rp = f"robots error: {e}"
        robots[base] = rp
    rp = robots[base]
    return rp if isinstance(rp, str) else rp.can_fetch(UA, url)

def get(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.status, r.headers.get("Content-Type", ""), r.read()

out = []
for url in URLS:
    row = {"url": url, "robots_allowed": allowed(url)}
    try:
        status, ctype, body = get(url)
        text = body.decode("utf-8", "replace")
        row.update(status=status, type=ctype, bytes=len(body), start=" ".join(text[:400].split()))
    except Exception as e:
        row["error"] = str(e)[:300]
    out.append(row)

# EU Funding & Tenders public search: multipart form with a "query" part.
row = {"url": SEDIA, "robots_allowed": allowed(SEDIA)}
try:
    boundary = "----fbhprobe"
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"query\"; filename=\"blob\"\r\n"
            f"Content-Type: application/json\r\n\r\n{json.dumps(SEDIA_QUERY)}\r\n--{boundary}--\r\n").encode()
    status, ctype, data = get(SEDIA, data=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    j = json.loads(data)
    row.update(status=status, total=j.get("totalResults"),
               sample=[{"title": (r.get("metadata", {}).get("title") or [r.get("summary")])[0],
                        "keys": sorted(r.get("metadata", {}).keys())[:40]} for r in j.get("results", [])[:3]])
except Exception as e:
    row["error"] = str(e)[:300]
out.append(row)
json.dump(out, open("probe_results.json", "w"), indent=1, default=str)
print(json.dumps(out, indent=1, default=str)[:3000])
