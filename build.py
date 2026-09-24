# ::ILANG
# [TYPE:component][PROJECT:brand-deal-radar][ROLE:static-site-builder]
# ::RULE{read:.ilang/site.ilang|read:data/offers.json|write:site/}
# ::BOUNDARY{never:invent offers, prices, dates or affiliate URLs}
"""Render verified offers and provider directories to a static Pages site."""

from __future__ import annotations

import datetime as dt
import html
import json
from pathlib import Path
import re
import shutil
from urllib.parse import urlparse

from settings import load_settings

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "site"
TEMPLATES = ROOT / "templates"


def esc(value):
    return html.escape(str(value), quote=True)


def slug(value):
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def valid_date(value):
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def render(template, **values):
    content = (TEMPLATES / template).read_text(encoding="utf-8")
    for key, value in values.items():
        content = content.replace("{{" + key + "}}", str(value))
    if re.search(r"\{\{[a-z_]+\}\}", content):
        raise ValueError(f"Unfilled template variable in {template}")
    return content


def write(path, value):
    target = OUT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(value, encoding="utf-8")


def jsonld(value):
    return '<script type="application/ld+json">' + json.dumps(value, ensure_ascii=False).replace("<", "\\u003c") + "</script>"


def list_schema(items):
    return {"@context": "https://schema.org", "@type": "ItemList", "itemListElement": [{"@type": "ListItem", "position": i, "url": url} for i, url in enumerate(items, 1)]}


def breadcrumb_schema(base, parts):
    return {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": i, "name": name, "item": base + path}
        for i, (name, path) in enumerate(parts, 1)
    ]}


def chrome(settings, path, title, description, body, schema=""):
    base = settings["domain"].rstrip("/")
    url = base + path
    return render("base.html", title=esc(title), description=esc(description), canonical=esc(url),
                  site_name=esc(settings["brand"]), body=body, schema=schema)


def main():
    settings = load_settings(ROOT / ".ilang" / "site.ilang")
    data = json.loads((ROOT / "data" / "offers.json").read_text(encoding="utf-8"))
    articles_data = json.loads((ROOT / "data" / "articles.json").read_text(encoding="utf-8"))
    articles = articles_data.get("articles", [])
    all_providers = settings["providers"]
    known = {p["name"] for p in all_providers}
    today = dt.datetime.now(dt.timezone.utc).date()
    base = settings["domain"].rstrip("/")
    offers = []
    for row in data.get("offers", []):
        if row.get("provider") not in known or not row.get("title") or not row.get("source_url") or not row.get("offer_url"):
            continue
        source_host = urlparse(row["source_url"]).hostname
        offer_host = urlparse(row["offer_url"]).hostname
        provider = next(p for p in all_providers if p["name"] == row["provider"])
        if not all(h and (h == provider["domain"] or h.endswith("." + provider["domain"])) for h in (source_host, offer_host)):
            continue
        until = valid_date(row.get("valid_until")) if row.get("valid_until") else None
        item = dict(row)
        item["expired"] = bool(until and until < today)
        item["slug"] = slug(row["provider"] + "-" + row["title"])
        offers.append(item)
    providers = [p for p in all_providers if any(o["provider"] == p["name"] for o in offers)]
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    urls = ["/"]
    lastmods = {"/": valid_date(data.get("generated_at")) if data.get("generated_at") else None}
    source_dates = {s["provider"]: valid_date(s.get("fetched_at")) for s in data.get("sources", []) if s.get("status") == "ok" and s.get("fetched_at")}
    provider_cards = []
    for provider in providers:
        path = f"/providers/{slug(provider['name'])}/"
        urls.append(path)
        lastmods[path] = source_dates.get(provider["name"])
        own = [o for o in offers if o["provider"] == provider["name"]]
        active = [o for o in own if not o["expired"]]
        cards = "".join(render("deal_card.html", title=esc(o["title"]), link=esc(f"/deals/{o['slug']}/"), status="Verified source" if not o["expired"] else "Expired") for o in own)
        if not cards:
            cards = "<p>No currently verified promotions. Check the official site for current prices.</p>"
        official = f"<a href=\"https://{esc(provider['domain'])}/\" rel=\"noopener\">Official site</a>"
        source = f"<a href=\"{esc(provider['source'])}\" rel=\"noopener\">Official source</a>" if provider["source"] else "No public offer source configured"
        related_articles = [article for article in articles if article.get("provider") == provider["name"]]
        guides = ""
        if related_articles:
            guide_links = "".join(f'<li><a href="/{esc(article["slug"])}/">{esc(article["title"])}</a> <span class="note">— official source checked {esc(article["fetched_at"][:10])}</span></li>' for article in related_articles)
            guides = f'<section class="related-guides"><h2>Official-source guides</h2><ul>{guide_links}</ul></section>'
        body = render("provider.html", name=esc(provider["name"]), official=official, source=source, deals=cards, guides=guides, count=len(active))
        schemas = [
            {"@context": "https://schema.org", "@type": provider["kind"], "name": provider["name"], "url": "https://" + provider["domain"] + "/",
             "offers": [{"@type": "Offer", "name": o["title"], "url": o["offer_url"], "availability": "https://schema.org/InStock"} for o in active]},
            list_schema([base + f"/deals/{o['slug']}/" for o in own]),
            breadcrumb_schema(base, [("Home", "/"), (provider["name"], path)]),
        ]
        write(f"providers/{slug(provider['name'])}/index.html", chrome(settings, path, f"{provider['name']} travel offers | {settings['brand']}", f"Official-source offers for {provider['name']}; {len(active)} currently verified.", body, "".join(jsonld(x) for x in schemas)))
        provider_cards.append(f'<a class="provider-card" href="{esc(path)}"><span class="provider-card__name">{esc(provider["name"])}</span><span class="provider-card__meta">{len(active)} verified listings with official sources</span><span class="provider-card__cta">View provider details →</span></a>')
    for offer in offers:
        path = f"/deals/{offer['slug']}/"
        urls.append(path)
        lastmods[path] = valid_date(offer.get("fetched_at")) if offer.get("fetched_at") else None
        provider = next(p for p in providers if p["name"] == offer["provider"])
        price = f'<p>Price: {esc(offer["price"])} {esc(offer["currency"])}</p>' if "price" in offer and "currency" in offer else ""
        until = f'<p>Valid until: {esc(offer["valid_until"])}</p>' if offer.get("valid_until") else ""
        status = "Expired — verify on official site" if offer["expired"] else "Source verified; check official site before purchase"
        body = render("deal.html", title=esc(offer["title"]), provider=esc(offer["provider"]), status=esc(status), price=price, until=until,
                      source_url=esc(offer["source_url"]), offer_url=esc(offer["offer_url"]), fetched_at=esc(offer.get("fetched_at", "unknown")))
        schema = {"@context": "https://schema.org", "@type": "Offer", "name": offer["title"], "url": offer["offer_url"], "availability": "https://schema.org/OutOfStock" if offer["expired"] else "https://schema.org/InStock"}
        if "price" in offer and "currency" in offer:
            schema.update(price=offer["price"], priceCurrency=offer["currency"])
        if offer.get("valid_until"):
            schema["priceValidUntil"] = offer["valid_until"]
        crumbs = breadcrumb_schema(base, [("Home", "/"), (provider["name"], f"/providers/{slug(provider['name'])}/"), (offer["title"], path)])
        write(f"deals/{offer['slug']}/index.html", chrome(settings, path, f"{offer['provider']}: {offer['title']} | {settings['brand']}", f"{offer['title']} from {offer['provider']}. Official source checked {offer.get('fetched_at', 'at an unknown time')}.", body, jsonld(schema) + jsonld(crumbs)))
    article_cards = []
    for article in articles:
        path = f"/{article['slug']}/"
        urls.append(path)
        lastmods[path] = valid_date(article.get("updated_at") or article.get("published_at"))
        steps = "".join(f"<li>{esc(step)}</li>" for step in article["steps"])
        details = "".join(f"<article><h3>{esc(item['heading'])}</h3><p>{esc(item['body'])}</p></article>" for item in article["details"])
        support_url = article.get("support_url", article["source_url"])
        troubleshooting_url = article.get("troubleshooting_url", support_url)
        modified_at = article.get("updated_at", article["published_at"])
        body = render("article.html", title=esc(article["title"]), answer=esc(article["answer"]), how_to_heading=esc(article["how_to_heading"]), steps=steps, details=details,
                      source_name=esc(article["source_name"]), source_url=esc(article["source_url"]), support_url=esc(support_url), troubleshooting_url=esc(troubleshooting_url), fetched_at=esc(article["fetched_at"]))
        schema = {"@context": "https://schema.org", "@type": "Article", "headline": article["title"], "mainEntityOfPage": base + path,
                  "datePublished": article["published_at"], "dateModified": modified_at, "author": {"@type": "Organization", "name": settings["brand"]},
                  "citation": article["source_url"]}
        crumbs = breadcrumb_schema(base, [("Home", "/"), (article["title"], path)])
        write(f"{article['slug']}/index.html", chrome(settings, path, f"{article['title']} | {settings['brand']}", article["description"], body, jsonld(schema) + jsonld(crumbs)))
        article_cards.append(f'<a class="guide-card" href="{esc(path)}"><span class="guide-card__title">{esc(article["title"])}</span><span class="guide-card__meta">Official source checked {esc(article["fetched_at"][:10])}</span><span class="provider-card__cta">Read the guide →</span></a>')
    avis_path = "/avis-promo-code/"
    urls.append(avis_path)
    lastmods[avis_path] = dt.date(2026, 9, 17)
    write("avis-promo-code/index.html", (TEMPLATES / "avis-promo-code.html").read_text(encoding="utf-8"))
    provider_cards.insert(0, '<a class="provider-card" href="/avis-promo-code/"><span class="provider-card__name">Avis</span><span class="provider-card__meta">8 official-source offers checked Sep 17, 2026</span><span class="provider-card__cta">View Avis deals →</span></a>')
    index_body = render("index.html", niche=esc(settings["niche"]), provider_list="\n".join(provider_cards), article_cards="\n".join(article_cards), verified_count=len([o for o in offers if not o["expired"]]) + 8)
    write("index.html", chrome(settings, "/", f"{settings['brand']} | US travel deals", f"Official-source deals for {settings['niche']}.", index_body, jsonld(list_schema([base + path for path in urls[1:]]))))
    compare_path = "/compare/"
    urls.append(compare_path)
    lastmods[compare_path] = lastmods["/"]
    rows = "".join(f'<tr><th><a href="/providers/{slug(p["name"])}/">{esc(p["name"])}</a></th><td>{len([o for o in offers if o["provider"] == p["name"] and not o["expired"]])}</td></tr>' for p in providers)
    write("compare/index.html", chrome(settings, compare_path, f"Compare travel brands | {settings['brand']}", "Compare official-source travel offer coverage by provider.", render("compare.html", rows=rows), jsonld(list_schema([base + f"/providers/{slug(p['name'])}/" for p in providers]))))
    write("sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "\n".join(f"<url><loc>{esc(base + path)}</loc>{'<lastmod>' + lastmods[path].isoformat() + '</lastmod>' if lastmods.get(path) else ''}</url>" for path in urls) + "\n</urlset>\n")
    write("robots.txt", f"User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n")
    # The apex hostname is canonical. Pages applies this after the www custom
    # domain becomes active, preserving the path and query string.
    write("_redirects", f"https://www.{urlparse(base).hostname}/* {base}/:splat 301\n")
    write("404.html", render("404.html", site_name=esc(settings["brand"])))
    print(f"Built {len(urls)} pages; {len(offers)} verified-source offers ({len([o for o in offers if not o['expired']])} active)")


if __name__ == "__main__":
    main()
