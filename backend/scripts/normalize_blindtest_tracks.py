"""
Script ponctuel (retour utilisateur, 2026-09-14) : réconciliation/
uniformisation des morceaux `Track` déjà importés dans la DB blindtest
(titres/artistes mal formatés selon la source d'import — entités HTML
résiduelles, forme unicode incohérente, espaces superflus, suffixes
techniques YouTube du style "(Official Video)").

Rejoue exactement les mêmes règles que `app/blindtest/text_cleanup.py`,
désormais aussi appliquées à chaque nouvel import (cf. `main_blindtest.py`,
`import_playlist`) — ce script ne rattrape que ce qui est déjà en base
avant ce changement.

Idempotent et re-lançable sans risque : ne réécrit une ligne `Track` que si
le nettoyage change réellement `title` ou `artist`, ne touche jamais
`youtube_video_id`/`isrc`/`duration_seconds`/les FK, et n'affecte aucune
autre table (pas de fusion de doublons entre playlists — `Track` est
volontairement scopé par playlist, cf. AD-7 ; le même morceau importé dans
deux playlists différentes reste deux lignes distinctes par conception).

Usage : cd backend && python scripts/normalize_blindtest_tracks.py
        [--dry-run] pour lister les changements sans les committer.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.blindtest.database import SessionLocal
from app.blindtest.models import Track
from app.blindtest.text_cleanup import clean_title_artist


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Affiche les changements sans les écrire en base.",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        tracks = db.query(Track).all()
        changed = 0
        for track in tracks:
            new_title, new_artist = clean_title_artist(track.title, track.artist)
            if new_title == track.title and new_artist == track.artist:
                continue

            changed += 1
            print(f"Track#{track.id}: {track.title!r}/{track.artist!r} -> {new_title!r}/{new_artist!r}")
            if not args.dry_run:
                track.title = new_title
                track.artist = new_artist

        if args.dry_run:
            print(f"\n[dry-run] {changed}/{len(tracks)} morceau(x) seraient modifiés, rien n'a été écrit.")
        else:
            db.commit()
            print(f"\n{changed}/{len(tracks)} morceau(x) modifié(s) et commité(s).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
