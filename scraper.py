# ::ILANG
# [TYPE:component][PROJECT:brand-deal-radar][ROLE:official-source-scraper]
# ::BOUNDARY{never:invent offers, prices, dates or affiliate URLs}
# ::RULE{read:.ilang/site.ilang|respect:robots.txt|write:data/offers.json}
"""Conservative, standard-library scraper of public official offer sources."""

from __future__ import annotations

import argparse
import datetime as dt
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
import xml.etree.ElementTree as ET

from settings import load_settings

ROOT = Path(__file__).resolve().parent
USER_AGENT = "BrandDealRadarBot/1.0 (+https://branddealradar.com/)"
KEYWORDS = re.compile(r"\b(sale|discount|coupon|promo(?:tion| code)?|offer|save)\b", re.I)


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.scripts = []
        self.links = []
        self._json_depth = 0
        self._chunks = []
        self.texts = []
        self._hidden_depth = 0

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "script" and values.get("type", "").lower() == "application/ld+json":
            self._json_depth = 1
            self._chunks = []
        if tag in ("script", "style"):
            self._hidden_depth += 1
        elif tag == "a" and values.get("href"):
            self.links.append(values["href"])

    def handle_data(self, data):
        if self._json_depth:
            self._chunks.append(data)
        elif not self._hidden_depth and data.strip():
            self.texts.append(data.strip())

    def handle_endtag(self, tag):
        if tag == "script" and self._json_depth:
            self.scripts.append("".join(self._chunks))
            self._json_depth = 0
        if tag in ("script", "style") and self._hidden_depth:
            self._hidden_depth -= 1


def explicit_code_offers(parser, provider, source_url, fetched_at):
    """Only extract an explicit code + discount sentence on an official page."""
    visible = " ".join(parser.texts)
    pattern = re.compile(
        r"Use(?:\s+promo)?\s+code\s+([A-Z0-9]{4,24})(?:\s+at\s+checkout)?\s+to\s+(?:get|save)\s+(\d{1,2})%\s+(?:off|on)\s+([^.!?]{1,100})[.!?]",
        re.I,
    )
    records = []
    for match in pattern.finditer(visible):
        code, percent, conditions = match.groups()
        title = clean_title(f"{percent}% off {conditions} with code {code}")
        records.append({"provider": provider["name"], "title": title, "offer_url": source_url, "source_url": source_url, "fetched_at": fetched_at})
    return records


def host_allowed(url, domain):
    host = (urllib.parse.urlsplit(url).hostname or "").lower()
    return host == domain or host.endswith("." + domain)


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xml,application/rss+xml;q=0.9,*/*;q=0.5"})
    with urllib.request.urlopen(req, timeout=12) as response:
        if response.status != 200:
            raise ValueError(f"HTTP {response.status}")
        data = response.read(2_000_001)
        if len(data) > 2_000_000:
            raise ValueError("source too large")
        return response.url, response.headers.get_content_type(), data.decode("utf-8", errors="replace")


def robots_allowed(url):
    parts = urllib.parse.urlsplit(url)
    robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
    try:
        _, _, body = fetch(robots_url)
    except (urllib.error.URLError, ValueError, TimeoutError) as exc:
        return False, f"robots.txt unavailable: {type(exc).__name__}"
    parser = urllib.robotparser.RobotFileParser()
    parser.parse(body.splitlines())
    return parser.can_fetch(USER_AGENT, url), "robots.txt"


def as_date(value):
    if not isinstance(value, str):
        return None
    candidate = value[:10]
    try:
        return dt.date.fromisoformat(candidate).isoformat()
    except ValueError:
        return None


def clean_title(value):
    return re.sub(r"\s+", " ", html.unescape(str(value))).strip()[:180]


def scan_jsonld(value, provider, source_url, fetched_at):
    records = []
    if isinstance(value, list):
        for item in value:
            records.extend(scan_jsonld(item, provider, source_url, fetched_at))
        return records
    if not isinstance(value, dict):
        return records
    typ = value.get("@type", "")
    types = typ if isinstance(typ, list) else [typ]
    if any(t in ("Product", "Service", "Event") for t in types):
        title = clean_title(value.get("name", ""))
        offers = value.get("offers", [])
        for offer in offers if isinstance(offers, list) else [offers]:
            if not isinstance(offer, dict) or not title or not KEYWORDS.search(title + " " + str(offer.get("name", ""))):
                continue
            raw_url = offer.get("url") or value.get("url") or source_url
            offer_url = urllib.parse.urljoin(source_url, str(raw_url))
            if not host_allowed(offer_url, provider["domain"]):
                continue
            name = clean_title(offer.get("name") or title)
            row = {"provider": provider["name"], "title": name, "offer_url": offer_url, "source_url": source_url, "fetched_at": fetched_at}
            price = offer.get("price")
            currency = offer.get("priceCurrency")
            if price is not None and re.fullmatch(r"\d+(?:\.\d{1,2})?", str(price)) and isinstance(currency, str) and re.fullmatch(r"[A-Z]{3}", currency):
                row.update(price=str(price), currency=currency)
            until = as_date(offer.get("priceValidUntil") or offer.get("validThrough"))
            if until:
                row["valid_until"] = until
            records.append(row)
    for key in ("@graph", "itemListElement", "mainEntity"):
        if key in value:
            records.extend(scan_jsonld(value[key], provider, source_url, fetched_at))
    return records


def scrape_rss(text, provider, source_url, fetched_at):
    records = []
    root = ET.fromstring(text)
    for item in list(root.findall(".//item")) + list(root.findall(".//{http://www.w3.org/2005/Atom}entry")):
        title = clean_title(item.findtext("title") or item.findtext("{http://www.w3.org/2005/Atom}title") or "")
        link = item.findtext("link")
        if not link:
            node = item.find("{http://www.w3.org/2005/Atom}link")
            link = node.get("href") if node is not None else None
        url = urllib.parse.urljoin(source_url, link or "")
        if title and KEYWORDS.search(title) and host_allowed(url, provider["domain"]):
            records.append({"provider": provider["name"], "title": title, "offer_url": url, "source_url": source_url, "fetched_at": fetched_at})
    return records


def scrape_provider(provider, fetched_at):
    source = provider["source"]
    if not source:
        return [], {"provider": provider["name"], "status": "no_public_source"}
    if not host_allowed(source, provider["domain"]):
        return [], {"provider": provider["name"], "status": "off_domain_source"}
    allowed, note = robots_allowed(source)
    if not allowed:
        return [], {"provider": provider["name"], "status": "robots_blocked_or_unavailable", "detail": note}
    try:
        final_url, content_type, body = fetch(source)
        if not host_allowed(final_url, provider["domain"]):
            raise ValueError("redirected off official domain")
        if content_type in ("application/rss+xml", "application/atom+xml"):
            rows = scrape_rss(body, provider, final_url, fetched_at)
        elif content_type in ("application/xml", "text/xml") or body.lstrip().startswith("<?xml"):
            # Sitemaps discover pages, not verified offers. Do not invent deals from URL slugs.
            rows = []
        else:
            parser = PageParser()
            parser.feed(body)
            rows = []
            for script in parser.scripts:
                try:
                    rows.extend(scan_jsonld(json.loads(script), provider, final_url, fetched_at))
                except json.JSONDecodeError:
                    pass
            rows.extend(explicit_code_offers(parser, provider, final_url, fetched_at))
        checked_at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
        return rows, {"provider": provider["name"], "status": "ok", "offers": len(rows), "source_url": final_url, "fetched_at": checked_at}
    except (urllib.error.URLError, ValueError, TimeoutError, ET.ParseError) as exc:
        return [], {"provider": provider["name"], "status": "fetch_error", "detail": type(exc).__name__}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    settings = load_settings(ROOT / ".ilang" / "site.ilang")
    fetched_at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    offers, sources = [], []
    providers = settings["providers"][:args.limit] if args.limit else settings["providers"]
    for provider in providers:
        rows, status = scrape_provider(provider, fetched_at)
        offers.extend(rows)
        sources.append(status)
        print(f"{provider['name']}: {status['status']} ({len(rows)} offers)")
    browser_verified_path = ROOT / "data" / "browser_verified_offers.json"
    if browser_verified_path.exists():
        browser_verified = json.loads(browser_verified_path.read_text(encoding="utf-8"))
        offers.extend(browser_verified.get("offers", []))
        sources.extend(browser_verified.get("sources", []))
    unique = {(r["provider"], r["offer_url"], r["title"]): r for r in offers}
    output = {"generated_at": fetched_at, "offers": list(unique.values()), "sources": sources}
    path = ROOT / "data" / "offers.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
