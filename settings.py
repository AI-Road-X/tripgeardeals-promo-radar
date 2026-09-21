# ::ILANG
# [TYPE:component][PROJECT:brand-deal-radar][ROLE:configuration-reader]
# ::RULE{read:.ilang/site.ilang|validate:required site and provider fields}
# ::BOUNDARY{never:substitute invented providers or sources}
"""Read the deliberately small I-Lang site configuration without a runtime dependency."""

from pathlib import Path
import re


def load_settings(path: Path) -> dict:
    content = path.read_text(encoding="utf-8")
    state = re.search(r"::STATE\{@SITE,\s*(.*?)\}", content)
    if not state:
        raise ValueError("Missing @SITE state")
    site = {}
    for part in state.group(1).split(","):
        key, separator, value = part.strip().partition(":")
        if separator:
            site[key.strip()] = value.strip()
    for key in ("brand", "niche", "domain", "locale"):
        if not site.get(key):
            raise ValueError(f"Missing site {key}")
    if not site["domain"].startswith("https://"):
        raise ValueError("Site domain must start with https://")
    providers = []
    in_providers = False
    for raw in content.splitlines():
        line = raw.strip()
        if line.startswith("::MODULE{PROVIDERS"):
            in_providers = True
            continue
        if in_providers and line.startswith("::MODULE{"):
            break
        if not in_providers or not line or line.startswith("::"):
            continue
        parts = [item.strip() for item in line.split("|")]
        if len(parts) not in (4, 5) or not parts[0] or not parts[1]:
            raise ValueError(f"Invalid provider row: {line}")
        kind = parts[4] if len(parts) == 5 else "Service"
        if kind not in ("Product", "Service"):
            raise ValueError(f"Invalid provider kind: {kind}")
        providers.append({"name": parts[0], "domain": parts[1], "source": "" if parts[2] == "无" else parts[2], "affiliate": parts[3], "kind": kind})
    if not providers:
        raise ValueError("No providers configured")
    return {**site, "providers": providers}
