"""
Script ponctuel (retour utilisateur, 2026-09-15) : supprime les `Playlist`
(et leurs `Track`, en cascade ORM — cf. `Playlist.tracks` dans
app/blindtest/models.py) importées il y a plus de `RETENTION_DAYS` jours et
jamais rejouées depuis.

Ne touche PAS `MatchCache` (app/blindtest/models.py) : cette table n'a
aucune relation avec `Playlist`/`Track` dans le schéma, elle persiste la
résolution `(isrc ou titre/artiste normalisé) -> youtube_video_id/durée`
indépendamment de toute playlist. C'est elle qui évite de re-solliciter
Deezer/YouTube pour un morceau déjà connu, même après suppression de la
playlist qui l'a fait connaître la première fois — l'objectif de ce script
(retour utilisateur : "garder les chansons [MatchCache] a une utilité pour
éviter un réimport, mais garder les playlists non utilisées ça ne sert à
rien") est donc atteint sans aucun risque de perdre ce bénéfice.

Garde-fou FK (SQLite, `PRAGMA foreign_keys = ON`) : `Game.current_track_id`
pointe vers un `Track` — avant de supprimer une playlist, ce script met
d'abord à `NULL` le `current_track_id` de toute partie qui pointait vers un
de ses morceaux (un pointeur vers "le dernier morceau tiré", sans signification
utile une fois la partie considérée abandonnée).

`RETENTION_DAYS = 30` (retour utilisateur) : en-deçà, une partie peut encore
être relancée via "Rejouer dans ce salon" (cf. `_handle_restart_game`,
main_blindtest.py) qui réutilise les playlists existantes — supprimer une
playlist trop tôt casserait ce rejeu pour une partie encore active.

Usage : cd backend && python scripts/prune_stale_blindtest_playlists.py
        [--dry-run] pour lister ce qui serait supprimé sans rien écrire.
        [--days N] pour ajuster le seuil de rétention (défaut 30).
"""
import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.blindtest.database import SessionLocal
from app.blindtest.models import Game, Playlist, Track

RETENTION_DAYS = 30


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Affiche ce qui serait supprimé sans rien écrire en base.",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=RETENTION_DAYS,
        help=f"Seuil de rétention en jours (défaut {RETENTION_DAYS}).",
    )
    args = parser.parse_args()

    cutoff = datetime.now(timezone.utc) - timedelta(days=args.days)

    db = SessionLocal()
    try:
        stale_playlists = db.query(Playlist).filter(Playlist.created_at < cutoff).all()
        if not stale_playlists:
            print(f"Aucune playlist de plus de {args.days} jours — rien à faire.")
            return

        stale_playlist_ids = {p.id for p in stale_playlists}
        total_tracks = sum(len(p.tracks) for p in stale_playlists)

        # Garde-fou FK : toute partie dont `current_track_id` pointe vers un
        # morceau d'une des playlists à supprimer doit d'abord être mise à
        # NULL, sinon la suppression échoue sur la contrainte FK.
        affected_games = (
            db.query(Game)
            .join(Track, Track.id == Game.current_track_id)
            .filter(Track.playlist_id.in_(stale_playlist_ids))
            .all()
        )

        for playlist in stale_playlists:
            print(
                f"Playlist#{playlist.id} ({playlist.provider}, {playlist.source_url}, "
                f"importée le {playlist.created_at:%Y-%m-%d}) : {len(playlist.tracks)} morceau(x)"
            )

        if args.dry_run:
            print(
                f"\n[dry-run] {len(stale_playlists)} playlist(s) / {total_tracks} morceau(x) "
                f"seraient supprimés, {len(affected_games)} partie(s) auraient leur "
                f"current_track_id remis à NULL, rien n'a été écrit."
            )
            return

        for game in affected_games:
            game.current_track_id = None
        for playlist in stale_playlists:
            db.delete(playlist)
        db.commit()

        print(
            f"\n{len(stale_playlists)} playlist(s) / {total_tracks} morceau(x) supprimé(s), "
            f"{len(affected_games)} partie(s) mise(s) à jour. MatchCache non touché."
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
