# ::ILANG
# [TYPE:component][PROJECT:tripgeardeals][ROLE:offline-checks]
# ::BOUNDARY{never:use test fixtures as published offers}
"""Offline configuration and output checks using temporary data only."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import build
import scraper
from settings import load_settings


class SiteTests(unittest.TestCase):
    def test_explicit_code_requires_official_sentence(self):
        parser = scraper.PageParser()
        parser.feed("<p>Use promo code FIRSTBOOKING to get 5% off your first booking.</p>")
        provider = {"name": "Bounce", "domain": "bounce.com"}
        rows = scraper.explicit_code_offers(parser, provider, "https://bounce.com/ls/coupons", "2026-09-20T00:00:00+00:00")
        self.assertEqual(rows[0]["title"], "5% off your first booking with code FIRSTBOOKING")
        self.assertNotIn("price", rows[0])
        self.assertNotIn("valid_until", rows[0])

    def make_root(self, folder):
        root = Path(folder)
        (root / ".ilang").mkdir()
        (root / "data").mkdir()
        (root / ".ilang" / "site.ilang").write_text(
            "::ILANG\n[TYPE:config][PROJECT:test][LANG:zh]\n"
            "::STATE{@SITE, brand:Test Brand, niche:US travel, domain:https://tripgeardeals-promo-radar.pages.dev, locale:en-US}\n"
            "::MODULE{PROVIDERS}\nExample | example.com | https://example.com/sale |\n",
            encoding="utf-8",
        )
        return root

    def test_provider_without_verified_offer_is_removed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = self.make_root(folder)
            (root / "data" / "offers.json").write_text('{"generated_at":null,"offers":[],"sources":[]}', encoding="utf-8")
            with patch.object(build, "ROOT", root), patch.object(build, "OUT", root / "site"):
                build.main()
                page = (root / "site" / "index.html").read_text(encoding="utf-8")
                self.assertNotIn("Example", page)
                self.assertIn('rel="canonical" href="https://tripgeardeals-promo-radar.pages.dev/"', page)
                self.assertFalse((root / "site" / "providers" / "example").exists())
                self.assertIn('content="noindex"', (root / "site" / "404.html").read_text(encoding="utf-8"))

    def test_missing_price_and_expired_offer(self):
        with tempfile.TemporaryDirectory() as folder:
            root = self.make_root(folder)
            data = {"generated_at": "2026-09-20T00:00:00+00:00", "sources": [], "offers": [
                {"provider": "Example", "title": "Sale offer", "offer_url": "https://example.com/sale", "source_url": "https://example.com/sale", "fetched_at": "2026-09-20T00:00:00+00:00", "valid_until": "2020-01-01"}
            ]}
            (root / "data" / "offers.json").write_text(json.dumps(data), encoding="utf-8")
            with patch.object(build, "ROOT", root), patch.object(build, "OUT", root / "site"):
                build.main()
            page = (root / "site" / "deals" / "example-sale-offer" / "index.html").read_text(encoding="utf-8")
            self.assertIn("Expired", page)
            self.assertNotIn('"price":', page)
            self.assertNotIn('"priceCurrency":', page)
            self.assertIn('"availability": "https://schema.org/OutOfStock"', page)
            self.assertIn("<lastmod>2026-09-20</lastmod>", (root / "site" / "sitemap.xml").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
