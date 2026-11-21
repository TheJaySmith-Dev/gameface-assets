# gameface-assets

Licence-cleared player cut-out images and metadata for the Gameface app.

```
TheSportsDB API (official endpoints only)
      ↓  licence gate + PNG validation + SHA-256 compare
this repo  (players/, metadata/players.json)
      ↓
Gameface app
```

## Using the assets in the app

- Metadata: `https://raw.githubusercontent.com/TheJaySmith-Dev/gameface-assets/main/metadata/players.json`
- Image: `https://raw.githubusercontent.com/TheJaySmith-Dev/gameface-assets/main/<image>` (or jsDelivr: `https://cdn.jsdelivr.net/gh/TheJaySmith-Dev/gameface-assets@main/<image>`)

`players.json` is keyed by `thesportsdb:<idPlayer>`, a stable ID that survives transfers. Each entry has
`image`, `team`, `season`, `status` (`active` / `inactive`), `sha256`, `licence`, `attribution` and `history`
(previous club images kept when a player moves). Paths look like
`players/premier-league/liverpool/<name>-<idPlayer>.png`. The ID suffix keeps two players with the same name apart.

Players without a cleared image are not in the file. Show a placeholder for them.

## Licensing rules (from TheSportsDB terms of use, checked 21 Nov 2026)

An image is stored only if `strCreativeCommons` is `Yes` **and** `strCreativeCommonsAttribution` names
CC0, public domain, CC BY or CC BY-SA. NonCommercial/NoDerivatives and anything unverified are skipped and logged.

Your obligations when showing these images:

- **Credits screen:** show each image's `attribution` (creator, licence, source link), plus "via TheSportsDB",
  and note it is a modified (cut-out) version.
- **CC BY-SA images** stay under CC BY-SA. Don't add DRM or extra restrictions.
- **Publicity rights:** a CC licence doesn't imply endorsement by the player, club or league.
- **App Store:** TheSportsDB requires a **paid API subscription** for apps published to an app store.
  Add the key as the repository secret `THESPORTSDB_API_KEY` before release. Without it the free key is used.
  The free key also caps results (about 10 teams × 10 players), so coverage stays partial and players
  are never marked inactive.

## Updating

- **Automatic:** 10 Feb and 10 Sep (edit the `cron` lines in `.github/workflows/update-player-images.yml`).
- **Manual:** Actions → Update player images → Run workflow.
- **PR or direct:** changes open a pull request by default. Set the repo variable `UPDATE_MODE=direct`
  to commit to `main`, or pick a mode when running it manually.
- **Locally:** `pip install -r requirements.txt && python scripts/update-player-images.py`

Unchanged source URLs are not re-downloaded. Files are rewritten only when their hash changes, and nothing is
committed when nothing changed.

### Overrides

`metadata/overrides.json` lets you correct the automatic pick:

```json
{
  "thesportsdb:34145506": { "exclude": true },
  "thesportsdb:34145423": { "image_url": "https://…", "attribution": "By X, CC BY 4.0, https://…" }
}
```

An override image must still carry an allowed licence in its attribution.

## Adding a competition

Add an entry to `competitions` in `config/sources.json` (TheSportsDB `league_id` and `league_name`).
For a different source, add a provider class in `scripts/providers/` with `current_season`, `teams`,
`players` and `download`, register it in `PROVIDERS`, and add its settings under `providers`.
