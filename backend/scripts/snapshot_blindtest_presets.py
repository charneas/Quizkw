"""
Rafraîchit `app/blindtest/presets/<slug>.json`, la copie de secours des
playlists préparées du blind test classique.

Le jeu relit la liste en direct à chaque sélection : ce fichier sert quand
YouTube ne répond pas, et ses noms relus priment pour les vidéos qu'il contient.
Un rafraîchissement conserve ces noms ; `raw_title` et `raw_channel` gardent la
source pour relire les nouveaux morceaux avant de committer.

Usage : cd backend && YOUTUBE_API_KEY=... python scripts/snapshot_blindtest_presets.py
        [--only <slug>] pour ne rafraîchir qu'un preset.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.blindtest.preset_tracks import live_tracks, playable_duration  # noqa: F401
from app.blindtest.presets import PRESETS, Preset

MIN_TRACKS = 10


def snapshot(preset: Preset) -> dict:
    return {
        "slug": preset.slug,
        "name": preset.name,
        "playlist_id": preset.playlist_id,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tracks": live_tracks(preset),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", choices=[preset.slug for preset in PRESETS], help="Ne rafraîchit que ce preset.")
    args = parser.parse_args()

    if not os.getenv("YOUTUBE_API_KEY"):
        sys.exit("YOUTUBE_API_KEY manquante.")

    for preset in PRESETS:
        if args.only and preset.slug != args.only:
            continue
        print(f"{preset.name}...")
        data = snapshot(preset)
        if len(data["tracks"]) < MIN_TRACKS:
            # Une réponse appauvrie ne doit pas écraser la copie de secours.
            sys.exit(f"  {len(data['tracks'])} morceaux seulement : {preset.path.name} inchangé.")
        preset.path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"  {len(data['tracks'])} morceaux écrits dans {preset.path.name}")


if __name__ == "__main__":
    main()
