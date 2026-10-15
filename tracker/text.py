"""Small helpers shared by the collectors."""

import http.cookiejar
import re
import time
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = "Mozilla/5.0 (compatible; heartfulness-funding-tracker; +https://github.com/martinbuess/heartfulness-funding-tracker)"


def drop_default_port(url):
    """'https://host:443/path' -> 'https://host/path'.

    data.ca.gov redirects to a signed S3 link written as s3.amazonaws.com:443.
    Python would send that port in the Host header, which breaks the
    signature and S3 answers 403.
    """
    parts = urllib.parse.urlsplit(url)
    default = {"https": 443, "http": 80}.get(parts.scheme)
    if parts.port is not None and parts.port == default:
        parts = parts._replace(netloc=parts.hostname)
    return urllib.parse.urlunsplit(parts)


class _RedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return super().redirect_request(req, fp, code, msg, headers, drop_default_port(newurl))


# The cookie jar lets sites that test for cookies with a redirect (MWRD) load.
_opener = urllib.request.build_opener(_RedirectHandler, urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


RETRY_WAIT = 60  # seconds before trying a site again after a server error


def fetch(url, timeout=300, data=None, headers=None):
    """Download a URL and return its bytes. Pass data (bytes) to POST.

    A server error (HTTP 5xx) is often a passing hiccup, so it is tried once
    more after a short wait before the source counts as failed.
    """
    request = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT, **(headers or {})})
    try:
        with _opener.open(request, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as error:
        if error.code < 500:
            raise
    time.sleep(RETRY_WAIT)
    with _opener.open(request, timeout=timeout) as resp:
        return resp.read()


def clean(text):
    """Strip HTML tags and entities and collapse whitespace."""
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    return re.sub(r"\s+", " ", text).strip()


def dollars(text):
    """'$1,250,000.00' -> '1250000'; blank when there is no usable amount."""
    match = re.search(r"\$?\s*([\d,]+)(?:\.\d+)?", text or "")
    if not match:
        return ""
    value = match.group(1).replace(",", "")
    return value if value.strip("0") else ""


_MONTHS = ("January|February|March|April|May|June|July|August|September|October|November|December|"
           "Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept|Sep|Oct|Nov|Dec")
# 15-Sep-2026, 15 September 2026, 15th Sep. 2026
_DMY = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?[\s-]+(" + _MONTHS + r")\.?,?[\s-]+(\d{4})\b", re.IGNORECASE)
# September 15, 2026
_MDY = re.compile(r"\b(" + _MONTHS + r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b", re.IGNORECASE)
_ISO = re.compile(r"\b(20\d\d)-(\d\d)-(\d\d)\b")


def dates(text):
    """Every date written in the text, in order, as datetime.date."""
    import datetime
    found = []
    for pattern, order in ((_DMY, "dmy"), (_MDY, "mdy"), (_ISO, "ymd")):
        for m in pattern.finditer(text or ""):
            if order == "dmy":
                day, month, year = m.groups()
            elif order == "mdy":
                month, day, year = m.groups()
            else:
                year, month, day = m.groups()
            try:
                if order == "ymd":
                    date = datetime.date(int(year), int(month), int(day))
                else:
                    date = datetime.datetime.strptime(f"{day} {month[:3]} {year}", "%d %b %Y").date()
            except ValueError:
                continue
            found.append((m.start(), date))
    return [d for _, d in sorted(found)]


def deadline_in(text):
    """The date written right after "deadline" (or "due", "closes", "apply by"); None if there isn't one."""
    for m in re.finditer(r"\b(deadline|due|closing date|closes|close on|apply (?:by|before)|submit (?:by|before)|last date)\b",
                         text or "", re.IGNORECASE):
        found = dates(text[m.end():m.end() + 60])
        if found:
            return found[0]
    return None
