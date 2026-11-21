#!/usr/bin/env python3
"""Fetch licence-cleared player cut-outs and keep players/ and metadata/players.json in sync.

Only images whose licence explicitly allows redistribution are stored. Everything else is
logged and skipped. Nothing is re-downloaded when the source URL is unchanged, and files are
only rewritten when their SHA-256 changes.
"""
import argparse
import datetime as dt
import hashlib
import io
import json
import re
import sys
import unicodedata
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from providers.thesportsdb import TheSportsDB  # noqa: E402

PROVIDERS = {"thesportsdb": TheSportsDB}
META = ROOT / "metadata" / "players.json"
OVERRIDES = ROOT / "metadata" / "overrides.json"


def slug(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def licence_of(attribution, policy):
    text = attribution.upper()
    if any(m in text for m in policy["rejected_markers"]):
        return None
    for lic in policy["allowed"]:  # most specific first (CC BY-SA before CC BY)
        m = re.search(re.escape(lic) + r"(?:\s*([0-9.]+))?", text)
        if m:
            return lic + (f" {m.group(1)}" if m.group(1) else "")
    return None


def validate_png(data, content_type, rules):
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return "not a PNG (got %s)" % (content_type or "unknown type")
    if len(data) < rules["min_bytes"]:
        return f"suspiciously small ({len(data)} bytes)"
    try:
        Image.open(io.BytesIO(data)).verify()
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception as e:  # noqa: BLE001
        return f"corrupt PNG ({e})"
    if img.width < rules["min_width"] or img.height < rules["min_height"]:
        return f"too small ({img.width}x{img.height})"
    if "A" not in img.getbands() and "transparency" not in img.info:
        return "no alpha channel"
    alpha = img.convert("RGBA").getchannel("A")
    hist = alpha.histogram()
    transparent = sum(hist[:250]) / (img.width * img.height)
    if transparent < rules["min_transparent_fraction"]:
        return f"not a cut-out (only {transparent:.0%} transparent)"
    return None


def load_json(path, default):
    return json.loads(path.read_text()) if path.exists() else default


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--competition", help="only update this competition slug")
    ap.add_argument("--summary", default="update-summary.md")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    cfg = json.loads((ROOT / "config" / "sources.json").read_text())
    meta = load_json(META, {"generated": None, "players": {}})
    overrides = load_json(OVERRIDES, {})
    players = meta["players"]
    counts = {"added": 0, "updated": 0, "unchanged": 0, "inactive": 0, "skipped_licence": 0,
              "no_image": 0, "errors": 0}
    log = []
    changed = False
    seasons = {}
    partial = False

    for comp in cfg["competitions"]:
        if not comp.get("enabled") or (args.competition and comp["slug"] != args.competition):
            continue
        provider = PROVIDERS[comp["provider"]](cfg["providers"][comp["provider"]])
        partial |= getattr(provider, "free_key", False)
        season = provider.current_season(comp)
        seasons[comp["name"]] = season
        seen = set()

        for team in provider.teams(comp):
            for p in provider.players(team):
                pid = f'{comp["provider"]}:{p["player_id"]}'
                seen.add(pid)
                ov = overrides.get(pid, {})
                if ov.get("exclude"):
                    continue
                url = ov.get("image_url") or p["image_url"]
                rec = players.get(pid)
                if not url:
                    counts["no_image"] += 1
                    continue
                lic = licence_of(ov.get("attribution") or p["attribution"], cfg["licence_policy"])
                if (p["creative_commons"] != "Yes" and not ov) or not lic:
                    counts["skipped_licence"] += 1
                    log.append(f"licence not cleared: {p['name']} ({team['name']}) "
                               f"cc={p['creative_commons'] or 'empty'} attribution={p['attribution'][:80] or 'none'}")
                    continue

                rel = f"players/{comp['slug']}/{slug(team['name'])}/{slug(p['name'])}-{p['player_id']}.png"
                same_source = rec and rec.get("source_url") == url and rec.get("image") == rel \
                    and (ROOT / rel).exists()
                if same_source:
                    if rec.get("status") != "active" or rec.get("season") != season:
                        rec.update(status="active", season=season)
                        changed = True
                    counts["unchanged"] += 1
                    continue

                try:
                    data, ctype = provider.download(url)
                except Exception as e:  # noqa: BLE001
                    counts["errors"] += 1
                    log.append(f"download failed: {p['name']}: {e}")
                    continue
                problem = validate_png(data, ctype, cfg["validation"])
                if problem:
                    counts["errors"] += 1
                    log.append(f"rejected image: {p['name']} ({team['name']}): {problem}")
                    continue
                digest = hashlib.sha256(data).hexdigest()

                history = list(rec.get("history", [])) if rec else []
                if rec and rec.get("image") and rec["image"] != rel:
                    history.append({"image": rec["image"], "team": rec.get("team"),
                                    "season": rec.get("season"), "sha256": rec.get("sha256")})
                if rec and rec.get("sha256") == digest and rec.get("image") == rel:
                    rec["source_url"] = url
                    counts["unchanged"] += 1
                    changed = True
                    continue

                if not args.dry_run:
                    (ROOT / rel).parent.mkdir(parents=True, exist_ok=True)
                    (ROOT / rel).write_bytes(data)
                players[pid] = {
                    "player_id": p["player_id"],
                    "id_source": comp["provider"],
                    "thesportsdb_id": p["player_id"] if comp["provider"] == "thesportsdb" else None,
                    "wikidata_id": p["wikidata_id"],
                    "name": p["name"],
                    "team": team["name"],
                    "team_id": team["id"],
                    "competition": comp["name"],
                    "season": season,
                    "status": "active",
                    "image": rel,
                    "sha256": digest,
                    "source_url": url,
                    "source_field": p["image_field"],
                    "licence": lic,
                    "attribution": ov.get("attribution") or p["attribution"],
                    "credit": "Image via TheSportsDB (thesportsdb.com)",
                    "modified": "transparent cut-out derived from the credited photo (via TheSportsDB)",
                    "history": history,
                    "updated": dt.date.today().isoformat(),
                }
                counts["updated" if rec else "added"] += 1
                changed = True

        if partial:
            log.append("free API key in use: results are capped by TheSportsDB, so players not returned "
                       "were NOT marked inactive")
        else:
            for pid, rec in players.items():
                if rec["competition"] == comp["name"] and rec["status"] == "active" and pid not in seen:
                    rec["status"] = "inactive"  # keep the file as a historical image
                    counts["inactive"] += 1
                    changed = True

    if changed and not args.dry_run:
        meta["generated"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        meta["seasons"] = seasons
        meta["players"] = dict(sorted(players.items()))
        META.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n")

    title = f"Player Image Update — {dt.date.today():%B %Y}"
    lines = [f"## {title}", "", *(f"- {k}: **{v}**" for k, v in seasons.items()), "",
             f"| Added | Updated | Unchanged | No longer active | Licence not cleared | No image | Errors |",
             "|---|---|---|---|---|---|---|",
             "| {added} | {updated} | {unchanged} | {inactive} | {skipped_licence} | {no_image} | {errors} |".format(**counts),
             ""]
    if log:
        lines += ["<details><summary>Log</summary>", "", *(f"- {l}" for l in log), "", "</details>"]
    Path(args.summary).write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"::notice::changed={str(changed).lower()}")


if __name__ == "__main__":
    main()
