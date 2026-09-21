# Brand Deal Radar

An English-language directory of US travel gear and service offers published at [branddealradar.com](https://branddealradar.com/).

Only public, official sources are queried. Missing prices, deadlines, or discounts are not inferred. A provider may be listed without a verified offer. No affiliate links are configured.

## Build locally

Python 3.12 or newer, standard library only:

```sh
python scraper.py
python build.py
```

`site/` is the Cloudflare Pages output directory. Configure Pages' build command as `python build.py` and output directory as `site` after the GitHub repository is connected. The scheduled workflow checks public sources every six hours and commits the resulting data and static pages if changed. Scheduled GitHub Actions may start later than the exact cron time.

Change providers, sources, brand or domain in `.ilang/site.ilang`; both scripts read that file. `data/offers.json` contains source status and any verifiable offers. Each offer records its official source and fetch time. Details with a missing price or date omit those fields from both HTML and JSON-LD.

Site rules are described in I-Lang: see `.ilang/site.ilang`; protocol information: ilang.ai.
