"""TheSportsDB provider. Uses only official API endpoints (their terms forbid scraping the website)."""
import json
import os
import time
import urllib.parse
import urllib.request

USER_AGENT = "gameface-assets-updater/1.0"


class TheSportsDB:
    def __init__(self, cfg):
        self.base = cfg["base_url"].rstrip("/")
        self.key = os.environ.get(cfg["api_key_env"]) or cfg["fallback_free_key"]
        self.free_key = self.key == cfg["fallback_free_key"]
        self.gap = float(cfg["min_seconds_between_requests"])
        self.image_fields = cfg["image_fields"]
        self._last = 0.0

    def _wait(self):
        delay = self.gap - (time.time() - self._last)
        if delay > 0:
            time.sleep(delay)
        self._last = time.time()

    def _get(self, url, retries=3):
        for attempt in range(retries):
            self._wait()
            try:
                req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
                with urllib.request.urlopen(req, timeout=30) as r:
                    return r.read(), r.headers.get("Content-Type", "")
            except Exception as e:  # noqa: BLE001
                if attempt == retries - 1:
                    raise
                time.sleep(5 * (attempt + 1))
                last = e
        raise RuntimeError(last)

    def _api(self, path, **params):
        url = f"{self.base}/{self.key}/{path}?{urllib.parse.urlencode(params)}"
        body, _ = self._get(url)
        return json.loads(body or b"{}")

    def current_season(self, comp):
        leagues = self._api("lookupleague.php", id=comp["league_id"]).get("leagues") or []
        return (leagues[0].get("strCurrentSeason") if leagues else None) or "unknown"

    def teams(self, comp):
        teams = self._api("search_all_teams.php", l=comp["league_name"]).get("teams") or []
        return [{"id": t["idTeam"], "name": t["strTeam"]} for t in teams]

    def players(self, team):
        rows = self._api("lookup_all_players.php", id=team["id"]).get("player") or []
        out = []
        for p in rows:
            if (p.get("strSport") or "Soccer") != "Soccer" or p.get("strPosition") == "Manager":
                continue
            image_url, field = None, None
            for f in self.image_fields:
                if p.get(f):
                    image_url, field = p[f], f
                    break
            out.append({
                "player_id": p["idPlayer"],
                "name": p["strPlayer"],
                "team": team["name"],
                "team_id": team["id"],
                "wikidata_id": p.get("idWikidata") or None,
                "image_url": image_url,
                "image_field": field,
                "creative_commons": (p.get("strCreativeCommons") or "").strip(),
                "attribution": (p.get("strCreativeCommonsAttribution") or "").strip(),
            })
        return out

    def download(self, url):
        return self._get(url)
