"""Small helpers shared by the collectors."""

import http.cookiejar
import re
import time
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = "Mozilla/5.0 (compatible; glia-funding-tracker; +https://github.com/gauravshikhargandhi-web/glia-funding-tracker)"


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
