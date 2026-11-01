"""Router du module blindtest — import de playlist publique (Epic 1, Story
1.1) et lobby/connexion temps réel (Epic 2, Story 2.1). Mirroir de
`main_games.py` pour la forme (APIRouter, Depends(get_db), limiter) mais
branché sur la DB isolée `app.blindtest.database` (AD-7).
"""
import asyncio
import logging
import random
from typing import List, Optional, Union

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.auth import require_admin_session
from app.blindtest import cache, classic, matching, preset_tracks, presets, schemas
from app.blindtest.database import SessionLocal, get_db
from app.blindtest.errors import (
    PrivatePlaylistError,
    ProviderConfigError,
    ProviderUnavailableError,
    UnrecognizedUrlError,
)
from app.blindtest.game_connections import classic_round_store, guess_store, played_tracks_store, score_store
from app.blindtest.game_connections import manager as connection_manager
from app.blindtest.import_pipeline import extract_tracks
from app.blindtest.song_identity import SongTrack, group_songs
from app.blindtest.text_cleanup import clean_title_artist
from app.blindtest.models import Game, Playlist, Track
from app.game_helpers import generate_session_code
from app.rate_limit import limiter

logger = logging.getLogger(__name__)

router = APIRouter()

# Story 2.6 : durée fixe (secondes) du minuteur serveur qui clôture un round
# si tous les joueurs présents non-propriétaires n'ont pas répondu avant.
# Module-level pour être monkeypatché par les tests (valeur réduite sur le
# chemin de test qui exerce réellement le timeout).
# Retour utilisateur (2026-09-14) : 30s jugé trop long pour un extrait —
# raccourci à 20s (durée de l'extrait ET du round, les deux sont couplés
# puisque l'audio joue pendant toute la fenêtre de devinette).
# Retour utilisateur (2026-11-01) : après essais, 20s jugé trop court —
# remonté à 30s.
ROUND_GUESS_SECONDS = classic.ROUND_SECONDS

# Story 2.7 : nombre de rounds joués par défaut avant fin de partie
# automatique (l'hôte peut désormais le personnaliser par partie, cf.
# `_rounds_target`/`_handle_start_game` ci-dessous — cette constante ne sert
# plus que de valeur par défaut/de secours), et durée (secondes) de la pause
# sur l'écran de reveal avant l'enchaînement automatique serveur vers le
# round suivant (ou la fin de partie). Module-level pour être monkeypatchées
# par les tests, même convention que `ROUND_GUESS_SECONDS`.
DEFAULT_ROUNDS_PER_GAME = 15
REVEAL_DISPLAY_SECONDS = 6

# Retour utilisateur (2026-09-14) : bornes du nombre de rounds personnalisable
# par l'hôte (`start_game {rounds}`) — un minimum de 1 (partie dégénérée mais
# valide) et un maximum raisonnable pour éviter une partie interminable/un
# pot de morceaux épuisé prématurément sur une petite playlist.
MIN_ROUNDS_PER_GAME = 1
MAX_ROUNDS_PER_GAME = 30

# `{game_id: nombre_de_rounds_choisi_par_l_hote}` — même convention en
# mémoire uniquement que `ScoreStore`/`PlayedTracksStore` (pas de colonne DB,
# ce module n'utilise que `Base.metadata.create_all`/pas d'Alembic, cf.
# `app/blindtest/database.py` : ajouter une colonne casserait la prod
# existante sans migration). Absent de ce dict -> `DEFAULT_ROUNDS_PER_GAME`.
_rounds_target: dict[int, int] = {}


def _get_rounds_target(game_id: int) -> int:
    return _rounds_target.get(game_id, DEFAULT_ROUNDS_PER_GAME)


# Retour utilisateur (2026-09-14) : un offset de départ tiré sur toute la
# durée du morceau pouvait démarrer à quelques secondes de la fin (silence,
# fade-out, générique) — l'extrait doit rester "de la musique" jusqu'au bout.
# On borne donc le dernier départ possible pour laisser au moins
# `MIN_SNIPPET_SECONDS` de lecture avant la fin du morceau — alignée sur
# `ROUND_GUESS_SECONDS` : pas besoin de garantir plus de musique
# restante que ce que le round laisse le temps d'écouter.
MIN_SNIPPET_SECONDS = ROUND_GUESS_SECONDS


def _pick_start_seconds(duration_seconds: int) -> int:
    """Tire l'offset de départ aléatoire d'un round : borné entre 0 et
    `duration_seconds - MIN_SNIPPET_SECONDS` pour garantir au moins
    `MIN_SNIPPET_SECONDS` de musique restante, quel que soit l'offset tiré.
    Pour un morceau plus court que `MIN_SNIPPET_SECONDS`, la seule borne
    valide est 0 (`_draw_eligible_track` exige de toute façon
    `duration_seconds > 0`)."""
    latest_start = max(0, duration_seconds - MIN_SNIPPET_SECONDS)
    return random.randint(0, latest_start)

# Story 8 (spec-blindtest-integration-ui, revue de code) : avant Story 8,
# `_draw_eligible_track` ne pouvait renvoyer `None` en cours de partie que si
# TOUS les morceaux du pot avaient réellement été joués -- `_advance_round`
# terminait alors la partie sans risque. Depuis que l'éligibilité dépend
# aussi de la connexion du propriétaire, `None` peut désormais survenir pour
# une raison transitoire (reload de page, coupure réseau brève) alors que des
# morceaux non-joués existent toujours -- terminer la partie direct dans ce
# cas serait irréversible pour une simple déconnexion passagère. Ces
# constantes bornent une petite fenêtre de grâce avant de considérer la
# situation comme définitive.
TRACK_POOL_RETRY_ATTEMPTS = 3
TRACK_POOL_RETRY_DELAY_SECONDS = 1.0

# Retour utilisateur (2026-09-13) : le propriétaire d'un morceau ne marquait
# jamais de points sur son propre round (delta figé à 0) — pénalisant pour
# quiconque importe une grosse playlist, dont les morceaux tournent plus
# souvent sans jamais lui rapporter de points. Point fixe accordé à chaque
# round, indépendamment de si les autres joueurs devinent juste ou pas.
OWNER_ROUND_BONUS = 1

CLASSIC_MODE = "classic"

# Blind test classique (spec-blindtest-classique) : nombre de titres choisi par
# l'hôte, validé côté serveur à chaque départ.
MIN_CLASSIC_ROUNDS = 10
MAX_CLASSIC_ROUNDS = 50
# Une réponse plus longue n'a aucune chance d'être légitime et ferait travailler
# la comparaison floue pour rien.
MAX_ANSWER_CHARS = 200
# Pause avant le titre suivant quand un round est annulé (vidéo bloquée).
VOIDED_ROUND_DELAY_SECONDS = 2

# Story 2.6 (revue de code) : référence forte vers la tâche `_round_timer` en
# vol de chaque partie, indexée par `game_id`. `asyncio.create_task` ne garde
# qu'une référence faible côté event loop — sans ceci, la tâche peut être
# ramassée par le GC avant de se déclencher (piège documenté d'asyncio),
# désactivant silencieusement le filet de sécurité de clôture en production.
# Indexer par `game_id` (plutôt qu'un simple `set`) permet aussi d'annuler
# immédiatement le minuteur d'un round clôturé par avance (`_close_round`,
# via `_cancel_round_timer`) au lieu de le laisser dormir inutilement jusqu'à
# `ROUND_GUESS_SECONDS` — sans ça, une connexion de test (ou un client réel)
# qui se ferme pendant que la tâche est encore en vol attend sa fin avant de
# pouvoir se terminer (constaté : ~30s de plus par test concerné).
_round_timer_tasks: dict = {}


def _cancel_round_timer(game_id: int) -> None:
    """Annule la tâche `_round_timer` encore en vol pour `game_id`, si elle
    existe. Ne s'auto-annule jamais : quand `_close_round` est appelé DEPUIS
    `_round_timer` lui-même (clôture par timeout), la tâche courante EST
    cette tâche — l'annuler ferait lever `CancelledError` au prochain
    `await` (le `broadcast` du `reveal` juste après), empêchant le message
    d'être envoyé."""
    task = _round_timer_tasks.pop(game_id, None)
    if task is not None and not task.done() and task is not asyncio.current_task():
        task.cancel()

# Codes de fermeture WS custom (plage 4400-4409, réservée à l'usage
# applicatif par la RFC 6455) — cf. Design Notes de
# spec-2-1-lobby-connexion-partie.md : pas de message `error` côté serveur,
# ces échecs surviennent tous avant/pendant la poignée de main initiale, sans
# pair établi à qui continuer de parler.
WS_CLOSE_UNKNOWN_GAME = 4404
WS_CLOSE_INVALID_PSEUDO = 4400
WS_CLOSE_DUPLICATE_PSEUDO = 4409

# Longueur max d'un pseudo accepté au join du lobby.
MAX_PSEUDO_LENGTH = 30

# Nombre max de tentatives de génération de code avant d'abandonner
# (garde-fou théorique — l'espace de code à 6 caractères rend une collision
# répétée quasi impossible).
MAX_CODE_GENERATION_ATTEMPTS = 5

# Réconciliation manuelle admin des morceaux non trouvés (spec
# spec-blindtest-admin-reconciliation.md) : même garde `require_admin_session`
# que les autres routes `/admin/*` (AD-17), branché sur la DB isolée
# blindtest (jamais de jointure/lecture croisée avec la DB principale).
admin_router = APIRouter(
    prefix="/admin/blindtest",
    tags=["Admin"],
    dependencies=[Depends(require_admin_session)],
)


def _validate_scope(body: schemas.PlaylistImportRequest, db: Session) -> Game | None:
    """Valide la paire `game_code`/`pseudo` d'un import scopé (Story 2.2) et
    renvoie le `Game` résolu (ou `None` pour un import anonyme). Lève une
    `HTTPException` sur toute violation de la matrice I/O de la spec — les
    deux champs sont toujours ensemble présents ou ensemble absents, le code
    doit référencer une partie existante en phase `lobby`, et le pseudo doit
    être actuellement connecté au lobby de cette partie (aucune `Player` DB
    table, seule la présence WS de Story 2.1 fait foi)."""
    if bool(body.game_code) != bool(body.pseudo):
        raise HTTPException(status_code=400, detail="game_code et pseudo doivent être fournis ensemble")

    if not body.game_code:
        return None

    game_code = body.game_code.upper()
    game = db.query(Game).filter(Game.code == game_code).first()
    if not game:
        raise HTTPException(status_code=404, detail="Partie introuvable")
    if game.phase != "lobby":
        raise HTTPException(status_code=400, detail="La partie n'est plus en phase de lobby")
    if not connection_manager.has_pseudo(game_code, body.pseudo.strip()):
        raise HTTPException(status_code=400, detail="Pseudo non connecté au lobby de cette partie")

    return game


def _require_classic_host(game: Game, pseudo: str) -> None:
    if pseudo.strip() != game.host_pseudo:
        raise HTTPException(status_code=403, detail="Seul l'hôte choisit la playlist")


def _replace_classic_source(db: Session, game: Game) -> None:
    """Une partie classique joue une seule playlist : la nouvelle remplace
    l'ancienne, dans la transaction de l'appelant (en lobby, aucun round ne
    référence ces morceaux)."""
    for playlist in db.query(Playlist).filter(Playlist.game_id == game.id).all():
        db.delete(playlist)
    db.flush()


def _playlist_response(db: Session, playlist: Playlist):
    """Les morceaux d'une partie classique sont les réponses du jeu : seuls les
    comptes sortent."""
    game = db.query(Game).filter(Game.id == playlist.game_id).first() if playlist.game_id else None
    if game is None or game.mode != CLASSIC_MODE:
        return playlist
    full = schemas.PlaylistResponse.model_validate(playlist)
    return schemas.RedactedPlaylistResponse(
        id=full.id,
        provider=full.provider,
        game_id=full.game_id,
        owner_pseudo=full.owner_pseudo,
        track_count=len(full.tracks),
        not_found_count=full.not_found_count,
        truncated=full.truncated,
    )


@router.post(
    "/blindtest/playlists",
    response_model=Union[schemas.PlaylistResponse, schemas.RedactedPlaylistResponse],
    status_code=201,
)
@limiter.limit("10/minute")
def import_playlist(
    request: Request,
    body: schemas.PlaylistImportRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Extrait une playlist publique (YouTube/Deezer) et persiste
    `Playlist` + `Track`. Échec propre sans écriture partielle :
    l'extraction complète a lieu avant tout `db.add`/`db.commit`.

    Story 2.2 : `game_code`/`pseudo` scopent optionnellement l'import à une
    partie — validés avant toute extraction (échec rapide, pas d'appel
    provider inutile) puisqu'ils ne dépendent que de l'état DB/WS, jamais du
    contenu de la playlist."""
    game = _validate_scope(body, db)
    if game and game.mode == CLASSIC_MODE:
        _require_classic_host(game, body.pseudo)

    try:
        provider, extracted = extract_tracks(body.url)
    except UnrecognizedUrlError:
        raise HTTPException(status_code=400, detail="URL de playlist non reconnue")
    except PrivatePlaylistError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except ProviderConfigError as exc:
        logger.error("Configuration provider manquante: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc))
    except ProviderUnavailableError as exc:
        # Panne côté provider (réseau, 5xx, 429, quota, corps invalide) : 502
        # explicite plutôt qu'un 500 brut ou un "playlist privée" trompeur.
        logger.warning("Provider indisponible pendant l'import: %s", exc)
        label = {"youtube": "YouTube", "deezer": "Deezer"}.get(exc.provider, exc.provider)
        raise HTTPException(status_code=502, detail=f"Service {label} indisponible, réessayez plus tard")

    # Re-vérification juste avant la persistance : `extract_tracks` est un
    # aller-retour réseau qui peut prendre plusieurs secondes, pendant
    # lesquelles la partie peut quitter la phase `lobby` ou le pseudo se
    # déconnecter. Sans ce second contrôle, la playlist serait tout de même
    # committée et scopée à un game/pseudo devenu obsolète (revue de code).
    game = _validate_scope(body, db)
    if game and game.mode == CLASSIC_MODE:
        _require_classic_host(game, body.pseudo)
        _replace_classic_source(db, game)

    playlist = Playlist(
        source_url=body.url,
        provider=provider,
        game_id=game.id if game else None,
        owner_pseudo=body.pseudo if game else None,
    )
    db.add(playlist)
    db.flush()  # obtenir playlist.id pour les FK des tracks, avant commit

    for item in extracted:
        # Retour utilisateur (2026-09-14) : "uniformisation dans la base de
        # données" — nettoyage non destructif (entités HTML, forme unicode,
        # espaces, suffixes "(Official Video)"...) appliqué à l'affichage dès
        # l'import, pour ne pas réintroduire le problème que
        # `scripts/normalize_blindtest_tracks.py` corrige sur l'existant.
        clean_title, clean_artist = clean_title_artist(item.title, item.artist)
        db.add(Track(
            playlist_id=playlist.id,
            title=clean_title,
            artist=clean_artist,
            isrc=item.isrc,
            youtube_video_id=item.youtube_video_id,
            source_url=item.source_url,
        ))
        if item.youtube_video_id:
            # Import direct YouTube : le morceau est déjà résolu, on
            # alimente le cache tout de suite pour qu'un futur import
            # Deezer du même morceau tape le cache (Story 1.3).
            # `duration_seconds=None` explicite (Story 2.3) : la durée n'est
            # pas encore connue à ce stade synchrone — c'est
            # `match_playlist_tracks` (tâche de fond planifiée juste après)
            # qui la récupérera et la persistera, jamais cette requête
            # player-facing (NFR1).
            cache.store(db, item.isrc, clean_title, clean_artist, item.youtube_video_id, duration_seconds=None)

    db.commit()
    db.refresh(playlist)

    matching.mark_matching(playlist.id)
    background_tasks.add_task(matching.match_playlist_tracks, playlist.id)

    return _playlist_response(db, playlist)


@router.get(
    "/blindtest/playlists/{playlist_id}",
    response_model=Union[schemas.PlaylistResponse, schemas.RedactedPlaylistResponse],
)
def get_playlist(playlist_id: int, db: Session = Depends(get_db)):
    """Permet au client de poller l'état de résolution (matching en tâche de
    fond) d'une playlist déjà importée."""
    playlist = db.query(Playlist).filter(Playlist.id == playlist_id).first()
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist introuvable")
    return _playlist_response(db, playlist)


@admin_router.get("/tracks/unresolved", response_model=List[schemas.UnresolvedTrackResponse])
def list_unresolved_tracks(db: Session = Depends(get_db)):
    """Liste, toutes playlists confondues, les morceaux jamais résolus par
    le matching automatique (`youtube_video_id IS NULL`) — pas de
    pagination (hors scope, cf. spec, pattern `AdminPropositions`)."""
    tracks = (
        db.query(Track)
        .join(Playlist, Track.playlist_id == Playlist.id)
        .options(joinedload(Track.playlist))
        .filter(Track.youtube_video_id.is_(None))
        .order_by(Track.id)
        .all()
    )
    return [
        schemas.UnresolvedTrackResponse(
            id=track.id,
            title=track.title,
            artist=track.artist,
            isrc=track.isrc,
            source_url=track.source_url,
            playlist_id=track.playlist_id,
            playlist_provider=track.playlist.provider,
        )
        for track in tracks
    ]


@admin_router.put("/tracks/{track_id}", response_model=schemas.TrackResponse)
def resolve_track(track_id: int, body: schemas.ResolveTrackRequest, db: Session = Depends(get_db)):
    """Résolution manuelle : accepte un lien YouTube complet (`watch?v=`,
    `youtu.be/`) ou un videoId nu (`extract_video_id`, partagé avec le
    matching automatique). Écrase toute valeur déjà présente (cas de
    correction — pas de restriction "null uniquement", cf. matrice I/O).
    Écrit aussi `MatchCache` (même priorité isrc puis clé normalisée que
    `cache.store`) pour que les imports futurs du même morceau bénéficient
    de cette résolution (FR3)."""
    track = db.query(Track).filter(Track.id == track_id).first()
    if not track:
        raise HTTPException(status_code=404, detail="Morceau introuvable")

    video_id = matching.extract_video_id(body.youtube_url)
    if not video_id:
        raise HTTPException(status_code=400, detail="Lien YouTube ou identifiant de vidéo invalide")

    # Story 2.3 : action admin low-frequency (pas player-facing, pas de
    # contrainte NFR1) — la durée est récupérée synchrone, dans la même
    # requête que la correction du `youtube_video_id`.
    duration = matching.fetch_video_duration(video_id)

    track.youtube_video_id = video_id
    if duration is not None:
        track.duration_seconds = duration
    cache.store(db, track.isrc, track.title, track.artist, video_id, duration_seconds=duration, overwrite=True)
    db.commit()
    db.refresh(track)
    return track


# === Lobby / connexion à une partie (Epic 2, Story 2.1) ===
#
# Troisième router de ce fichier (à côté de `router`/`admin_router`, cf.
# Code Map de la spec) : création de partie + canal WebSocket de lobby.
# Reste isolé de la DB principale Quizkw (AD-4/AD-7) : seul le helper pur
# `generate_session_code` est réutilisé, jamais `main_games.py` lui-même.
game_router = APIRouter()


@game_router.post("/blindtest/games", response_model=schemas.GameCreateResponse, status_code=201)
@limiter.limit("10/minute")
def create_game(
    request: Request,
    body: Optional[schemas.GameCreateRequest] = None,
    db: Session = Depends(get_db),
):
    """Crée une partie de blind test avec un code unique à 6 caractères.

    Même boucle de génération-et-vérification de collision que
    `main_games.create_game`, mais contre la table `Game` isolée du module
    blindtest (jamais contre `GameSession` de la DB principale).

    La vérification préalable (`filter(Game.code == code).first()`) laisse
    une fenêtre de course entre deux requêtes concurrentes : la contrainte
    unique sur `code` reste le garde-fou final, donc l'insertion elle-même
    est protégée par une boucle de retry bornée sur `IntegrityError`.

    Sans corps, la partie est en mode "owner"."""
    mode = body.mode if body else "owner"
    for attempt in range(MAX_CODE_GENERATION_ATTEMPTS):
        code = generate_session_code()
        while db.query(Game).filter(Game.code == code).first():
            code = generate_session_code()

        game = Game(code=code, phase="lobby", mode=mode)
        db.add(game)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            continue
        db.refresh(game)
        return game

    raise HTTPException(status_code=500, detail="Impossible de générer un code de partie unique")


def _classic_game_or_404(db: Session, code: str) -> Game:
    game = db.query(Game).filter(Game.code == code.upper()).first()
    if not game:
        raise HTTPException(status_code=404, detail="Partie introuvable")
    if game.mode != CLASSIC_MODE:
        raise HTTPException(status_code=400, detail="Cette partie n'est pas en mode classique")
    return game


def _classic_playable_count(db: Session, game: Game) -> int:
    """Nombre de chansons différentes prêtes à être jouées : un morceau reste
    injouable tant que sa durée n'est pas connue."""
    return sum(1 for copies in _unplayed_songs(db, game).values() if _drawable_tracks(game, copies))


def _classic_source(db: Session, game: Game) -> schemas.ClassicSourceResponse:
    playlist = db.query(Playlist).filter(Playlist.game_id == game.id).first()
    if playlist is None:
        return schemas.ClassicSourceResponse(name=None, playable_count=0)
    preset = presets.preset_from_source_url(playlist.source_url)
    return schemas.ClassicSourceResponse(
        name=preset.name if preset else "Playlist importée",
        playable_count=_classic_playable_count(db, game),
        checking=matching.is_matching(playlist.id),
    )


@game_router.get("/blindtest/presets", response_model=List[schemas.PresetResponse])
def list_presets():
    return [
        schemas.PresetResponse(slug=preset.slug, name=preset.name, track_count=len(presets.load_tracks(preset)))
        for preset in presets.available_presets()
    ]


def _check_preset_selection(game: Game, pseudo: str) -> None:
    if game.phase != "lobby":
        raise HTTPException(status_code=400, detail="La partie n'est plus en phase de lobby")
    _require_classic_host(game, pseudo)
    if not connection_manager.has_pseudo(game.code, pseudo.strip()):
        raise HTTPException(status_code=400, detail="Pseudo non connecté au lobby de cette partie")


def _preset_tracks(preset: presets.Preset) -> List[dict]:
    """La liste du moment, ou la copie locale si YouTube ne répond pas ou
    renvoie trop peu de morceaux pour une partie."""
    try:
        tracks = preset_tracks.live_tracks(preset)
    except Exception as exc:
        # Le type seul : le message d'une erreur httpx contient l'URL, donc la
        # clé API. Toute panne, même une réponse inattendue, doit se replier.
        logger.warning("Preset %s lu depuis la copie locale : %s", preset.slug, type(exc).__name__)
        return presets.load_tracks(preset)
    if len(tracks) < MIN_CLASSIC_ROUNDS:
        logger.warning("Preset %s lu depuis la copie locale : %s morceaux en direct", preset.slug, len(tracks))
        return presets.load_tracks(preset)
    return tracks


@game_router.post("/blindtest/games/{code}/preset", response_model=schemas.ClassicSourceResponse)
@limiter.limit("20/minute")
def select_preset(request: Request, code: str, body: schemas.PresetSelectRequest, db: Session = Depends(get_db)):
    """L'hôte joue une playlist préparée, relue en direct : ses durées arrivent
    avec la liste, rien ne part en tâche de fond."""
    game = _classic_game_or_404(db, code)
    _check_preset_selection(game, body.pseudo)
    preset = presets.find_preset(body.slug)
    if preset is None:
        raise HTTPException(status_code=404, detail="Playlist préparée introuvable")

    # Avant toute écriture : l'aller-retour YouTube ne doit pas tenir une
    # transaction ouverte, ni effacer la source actuelle s'il échoue. L'hôte ou
    # la phase ont pu changer pendant l'attente.
    db.rollback()
    tracks = _preset_tracks(preset)
    db.refresh(game)
    _check_preset_selection(game, body.pseudo)

    _replace_classic_source(db, game)
    playlist = Playlist(
        source_url=preset.source_url,
        provider="preset",
        game_id=game.id,
        owner_pseudo=game.host_pseudo,
    )
    db.add(playlist)
    db.flush()
    for item in tracks:
        db.add(Track(
            playlist_id=playlist.id,
            title=item["title"],
            artist=item["artist"],
            youtube_video_id=item["youtube_video_id"],
            duration_seconds=item["duration_seconds"],
        ))
    db.commit()
    return _classic_source(db, game)


@game_router.get("/blindtest/games/{code}/source", response_model=schemas.ClassicSourceResponse)
def get_classic_source(code: str, db: Session = Depends(get_db)):
    return _classic_source(db, _classic_game_or_404(db, code))


def _draw_eligible_track(db: Session, game: Game) -> Optional[Track]:
    """Tire aléatoirement un morceau éligible du pot de cette partie (Story
    2.4, extrait en Story 2.7 pour être partagé avec l'enchaînement
    automatique des rounds suivants) : scopé à `game.id`, résolu
    (`youtube_video_id` connu) et de durée connue et positive.

    Story 2.7 : exclut aussi tout morceau déjà tiré plus tôt dans cette même
    partie (`played_tracks_store`) — un round ne peut jamais rejouer un
    morceau déjà passé, du round 1 (via cette même fonction) à tous les
    suivants. Le filtre `notin_` n'est appliqué que si l'ensemble est
    non-vide : une clause `NOT IN ()` vide se comporte différemment (parfois
    toujours fausse) selon les moteurs SQL, mieux vaut l'éviter explicitement
    plutôt que de compter sur SQLAlchemy pour bien la neutraliser.

    Story 8 (spec-blindtest-integration-ui) : exclut aussi tout morceau dont
    le propriétaire (`Playlist.owner_pseudo`) n'est plus connecté à cette
    partie. Comme l'éligibilité est recalculée à chaque tirage (rien n'est
    mis en cache), ce filtre retire ET réintègre automatiquement les
    morceaux d'un joueur au fil de ses déconnexions/reconnexions, sans état
    supplémentaire à gérer. `.in_([])` (aucun joueur connecté) est un SQL
    bien défini — contrairement au piège `notin_([])` documenté ci-dessus,
    pas besoin de garde explicite ici.

    En mode classique, personne ne possède les morceaux : la connexion des
    joueurs n'entre pas en compte."""
    is_classic = game.mode == CLASSIC_MODE
    connected_pseudos = set(connection_manager.players(game.code))
    # Tirage en deux temps : la chanson d'abord, la copie ensuite. Une chanson
    # présente dans trois playlists n'a pas trois fois plus de chances de
    # sortir, et reste tirable dès qu'un de ses propriétaires est connecté,
    # même si la copie jouable est celle d'un joueur déconnecté.
    drawable_songs = []
    for copies in _unplayed_songs(db, game).values():
        playable = _drawable_tracks(game, copies)
        if playable and (is_classic or any(playlist.owner_pseudo in connected_pseudos for _, playlist in copies)):
            drawable_songs.append(playable)
    if not drawable_songs:
        return None
    return random.choice(random.choice(drawable_songs))


def _is_playable(track: Track) -> bool:
    return bool(track.youtube_video_id) and bool(track.duration_seconds) and track.duration_seconds > 0


def _classic_reference(track: Track, playlist: Playlist) -> classic.Reference:
    return classic.build_reference(track.title, track.artist, structured=playlist.provider != "youtube")


def _drawable_tracks(game: Game, copies: list) -> list:
    """Les copies jouables d'une chanson. En mode classique, il faut aussi que
    le titre et l'artiste puissent être trouvés : une chaîne vide ne laisserait
    aucune réponse possible pour l'artiste."""
    tracks = []
    for track, playlist in copies:
        if not _is_playable(track):
            continue
        if game.mode == CLASSIC_MODE:
            reference = _classic_reference(track, playlist)
            if not reference.titles or not reference.artists:
                continue
        tracks.append(track)
    return tracks


def _game_tracks(db: Session, game: Game) -> list:
    """Tous les morceaux de la partie avec leur playlist, y compris ceux pas
    encore résolus : un joueur dont la copie n'a pas (encore) de vidéo possède
    quand même la chanson."""
    return (
        db.query(Track, Playlist)
        .join(Playlist, Track.playlist_id == Playlist.id)
        .filter(Playlist.game_id == game.id)
        .order_by(Track.id)
        .all()
    )


def _song_of_each_track(rows: list) -> dict[int, int]:
    return group_songs(
        SongTrack(
            id=track.id,
            title=track.title,
            artist=track.artist,
            isrc=track.isrc,
            youtube_video_id=track.youtube_video_id,
            duration_seconds=track.duration_seconds,
            structured=playlist.provider != "youtube",
        )
        for track, playlist in rows
    )


def _unplayed_songs(db: Session, game: Game) -> dict[int, list]:
    """`{song_id: [(track, playlist), ...]}` des chansons pas encore tirées dans
    cette partie. Retour utilisateur (2026-09-14) : "même musique dans
    différentes playlists = même musique" — `played_tracks_store` retient des
    `youtube_video_id`, mais une chanson est jouée dès qu'UNE de ses copies
    l'est, y compris quand les playlists pointent vers des vidéos différentes
    (cf. `song_identity`)."""
    rows = _game_tracks(db, game)
    songs = _song_of_each_track(rows)
    played_video_ids = played_tracks_store.played_ids(game.id)
    played_songs = {songs[track.id] for track, _ in rows if track.youtube_video_id in played_video_ids}

    unplayed: dict[int, list] = {}
    for track, playlist in rows:
        if songs[track.id] not in played_songs:
            unplayed.setdefault(songs[track.id], []).append((track, playlist))
    return unplayed


def _has_unplayed_track(db: Session, game: Game) -> bool:
    """Story 8 (revue de code) : variante de `_draw_eligible_track` SANS le
    filtre de connexion — sert uniquement à distinguer un pot réellement
    épuisé (aucun morceau non-joué, peu importe qui est connecté) d'un pot
    temporairement vide parce que les propriétaires restants sont
    déconnectés. `_advance_round` s'en sert pour décider si la fin de partie
    est définitive ou seulement transitoire."""
    return any(_drawable_tracks(game, copies) for copies in _unplayed_songs(db, game).values())


def _game_state_extra(game: Game) -> dict:
    return {"phase": game.phase, "host_pseudo": game.host_pseudo, "mode": game.mode}


def _round_payload(game: Game, track: Track, start_seconds: int) -> dict:
    """Payload `round_started`. En mode classique, le titre et l'artiste sont la
    réponse : ils restent côté serveur, et le chrono de la manche démarre ici,
    juste avant la diffusion."""
    if game.mode == CLASSIC_MODE:
        payload = {
            "videoId": track.youtube_video_id,
            "startSeconds": start_seconds,
            "trackId": track.id,
            "durationSeconds": ROUND_GUESS_SECONDS,
        }
        classic_round_store.begin(game.id, track.id, _classic_reference(track, track.playlist), payload)
        return payload
    return {
        "videoId": track.youtube_video_id,
        "startSeconds": start_seconds,
        "title": track.title,
        "artist": track.artist,
        # Identifiant du round renvoyé par le client dans chaque
        # `guess_submitted` : une devinette en retard (round précédent) est
        # ignorée par `_handle_guess_submitted`.
        "trackId": track.id,
    }


def _classic_start_refusal(db: Session, game: Game, requesting_pseudo: str, payload: Optional[dict]) -> Optional[dict]:
    """Motif du refus d'un `start_game` classique, à montrer à l'hôte. `None`
    si le départ peut se faire, ou si ce message ne le concerne pas (autre mode,
    non-hôte, mauvaise phase : `_handle_start_game` reste un no-op silencieux)."""
    db.refresh(game)
    if game.mode != CLASSIC_MODE or requesting_pseudo != game.host_pseudo or game.phase != "lobby":
        return None

    rounds = payload.get("rounds") if isinstance(payload, dict) else None
    if not isinstance(rounds, int) or isinstance(rounds, bool) or not MIN_CLASSIC_ROUNDS <= rounds <= MAX_CLASSIC_ROUNDS:
        return {
            "reason": "invalid_rounds",
            "message": f"Choisis entre {MIN_CLASSIC_ROUNDS} et {MAX_CLASSIC_ROUNDS} titres.",
        }

    playable = _classic_playable_count(db, game)
    if playable < MIN_CLASSIC_ROUNDS:
        return {
            "reason": "pool_too_small",
            "message": f"Seulement {playable} titre(s) jouable(s) : il en faut au moins {MIN_CLASSIC_ROUNDS}.",
            "playable_count": playable,
        }
    return None


def _handle_start_game(db: Session, game: Game, requesting_pseudo: str, payload: Optional[dict] = None) -> Optional[dict]:
    """Traite un message `start_game` (Story 2.4) : vérifie hôte/phase, tire
    un morceau éligible du pot de cette partie, calcule un offset de départ
    aléatoire et fait passer la partie en `round_started`.

    Retour utilisateur (2026-09-14) : `payload` porte désormais optionnellement
    `rounds` — le nombre de rounds choisi par l'hôte pour CETTE partie,
    enregistré dans `_rounds_target` avant le tirage du premier round. Une
    valeur absente/invalide (pas un int, hors bornes `MIN`/`MAX_ROUNDS_PER_GAME`)
    est silencieusement ignorée et laisse `DEFAULT_ROUNDS_PER_GAME` en vigueur
    plutôt que de faire échouer tout le `start_game` pour un souci de forme sur
    un champ optionnel.

    Renvoie le payload `round_started {videoId, startSeconds, title, artist}`
    à diffuser,
    ou `None` si une vérification échoue (non-hôte, phase déjà avancée, pot
    vide) — l'appelant ne diffuse alors rien (no-op silencieux, cf. matrice
    I/O : ni close, ni message d'erreur, ces cas sont défense-en-profondeur
    puisque le frontend ne montre le contrôle qu'à l'hôte)."""
    db.refresh(game)
    if requesting_pseudo != game.host_pseudo:
        return None
    if game.phase != "lobby":
        return None

    rounds = payload.get("rounds") if isinstance(payload, dict) else None
    if game.mode == CLASSIC_MODE:
        # Déjà validé par `_classic_start_refusal`. Plus de titres demandés que
        # de jouables : la partie joue tout ce qu'il y a.
        _rounds_target[game.id] = min(rounds, _classic_playable_count(db, game))
    elif isinstance(rounds, int) and not isinstance(rounds, bool) and MIN_ROUNDS_PER_GAME <= rounds <= MAX_ROUNDS_PER_GAME:
        _rounds_target[game.id] = rounds

    track = _draw_eligible_track(db, game)
    if track is None:
        return None

    start_seconds = _pick_start_seconds(track.duration_seconds)

    game.phase = "round_started"
    game.current_track_id = track.id
    db.commit()

    # Story 2.7 : ce premier round n'était jusqu'ici jamais enregistré dans
    # `played_tracks_store` (la story n'existait pas encore) — désormais
    # tout tirage, y compris le tout premier de la partie, y est enregistré
    # pour que l'exclusion et le compte de rounds joués s'appliquent
    # uniformément dès le round 1 (cf. Code Map de la spec).
    #
    # Retour utilisateur (2026-09-14) : enregistré par `youtube_video_id`
    # (la vraie chanson), pas par `track.id` — cf. `_draw_eligible_track`.
    played_tracks_store.add(game.id, track.youtube_video_id)

    # Story 2.5 : un nouveau round tiré invalide toute devinette encore en
    # mémoire pour le round précédent — sans ça, une devinette non
    # resoumise par un joueur silencieux survivrait au changement de round
    # et serait scorée à tort par Story 2.6/2.7 (Boundaries de la spec).
    guess_store.reset_round(game.id)

    return _round_payload(game, track, start_seconds)


def _handle_restart_game(db: Session, game: Game, requesting_pseudo: str) -> bool:
    """Traite un message `restart_game` (retour utilisateur 2026-09-14 :
    "rejouer dans le même salon") : ramène une partie `ended` en `lobby`
    dans le même salon (même `code`/`game_id`, mêmes playlists importées),
    pour rejouer sans que chacun ait à ressaisir un lien/code.

    Mêmes gardes que `_handle_start_game` (hôte + phase attendue), même
    convention de retour no-op silencieux (`False`) si l'une échoue —
    défense en profondeur, le bouton n'est déjà montré qu'à l'hôte sur
    l'écran `ended`.

    Remet à zéro l'état en mémoire de la partie précédente
    (`played_tracks_store`/`score_store`/`guess_store`) : sans ça, la
    nouvelle partie hériterait des morceaux déjà tirés et des scores
    cumulés de la précédente au lieu de repartir de zéro. Ne touche pas aux
    `Playlist`/`Track` importées (scopées à `game.id`, réutilisées telles
    quelles) ni à `host_pseudo` (inchangé, même hôte)."""
    db.refresh(game)
    if requesting_pseudo != game.host_pseudo:
        return False
    if game.phase != "ended":
        return False

    game.phase = "lobby"
    game.current_track_id = None
    db.commit()

    played_tracks_store.reset_game(game.id)
    score_store.reset_game(game.id)
    guess_store.reset_round(game.id)
    classic_round_store.finish(game.id)

    return True


def _resolve_owner_pseudos(db: Session, game: Game) -> list[str]:
    """Tous les joueurs de la partie qui possèdent la chanson du round en
    cours, connectés ou non : le propriétaire du morceau tiré d'abord, les
    autres par ordre alphabétique. Vide si `current_track_id` n'est pas
    renseigné (défensif, ne devrait pas arriver une fois `phase ==
    "round_started"`)."""
    rows = _game_tracks(db, game)
    songs = _song_of_each_track(rows)
    current_song = songs.get(game.current_track_id)
    if current_song is None:
        return []
    drawn_owner = next(playlist.owner_pseudo for track, playlist in rows if track.id == game.current_track_id)
    others = {
        playlist.owner_pseudo
        for track, playlist in rows
        if songs[track.id] == current_song and playlist.owner_pseudo
    } - {drawn_owner}
    return ([drawn_owner] if drawn_owner else []) + sorted(others)


def _classic_round_points(finds: dict) -> int:
    return classic.points(
        classic.TITLE in finds,
        classic.ARTIST in finds,
        (finds.get(classic.TITLE, 0), finds.get(classic.ARTIST, 0)),
    )


def _close_classic_round(game: Game, game_code: str) -> dict:
    """Payload `reveal` classique. Les points sont déjà dans `score_store`,
    ajoutés à chaque découverte : il ne reste qu'à faire apparaître au classement
    les joueurs qui n'ont rien trouvé."""
    current = classic_round_store.finish(game.id)
    deltas = {}
    for pseudo in set(connection_manager.players(game_code)) | set(current.finds):
        score_store.add(game.id, pseudo, 0)
        deltas[pseudo] = _classic_round_points(current.found_by(pseudo))
    return {
        "title": current.reference.title,
        "artist": current.reference.artist,
        "deltas": deltas,
        "scores": score_store.snapshot(game.id),
    }


def _close_round(db: Session, game: Game, game_code: str) -> Optional[dict]:
    """Clôture le round en cours (Story 2.6) : calcule et cumule le score de
    chaque joueur présent non-propriétaire à partir de sa devinette stockée
    (`guess_store`), attribue OWNER_ROUND_BONUS à chaque propriétaire (retour
    utilisateur, 2026-09-13 — sans ça, importer une grosse playlist désavantage
    son propriétaire : ses morceaux tournent plus souvent sans jamais lui
    rapporter de points), fait passer la partie en phase `reveal` et renvoie
    le payload `reveal {owner_pseudo, owner_pseudos, scores, deltas}` à
    diffuser. `owner_pseudo` reste le propriétaire du morceau tiré ;
    `owner_pseudos` les liste tous, quand plusieurs joueurs ont la chanson.

    Transition à usage unique (mirroir de `_handle_start_game`) : si la
    partie n'est plus en `round_started` au moment de l'appel (déjà clôturée
    par l'autre chemin d'appel — clôture anticipée vs minuteur), no-op
    silencieux qui renvoie `None` — c'est ce qui rend inoffensif un minuteur
    qui se déclenche après une clôture anticipée, et vice versa.

    La clôture anticipée et le minuteur tournent sur deux sessions DB
    distinctes : un `SELECT` (`db.refresh`) puis un `if` séparé serait un
    check-then-act non atomique — les deux pourraient lire `round_started`
    avant que l'un des deux n'ait commité la transition, et scorer tout le
    monde deux fois (revue de code, race confirmée par exécutions répétées).
    La transition de phase sert donc elle-même de verrou : l'`UPDATE ...
    WHERE phase = 'round_started'` ne peut affecter une ligne que pour un
    seul appelant, quel que soit le nombre de sessions qui le tentent en
    même temps."""
    claimed = (
        db.query(Game)
        .filter(Game.id == game.id, Game.phase == "round_started")
        .update({"phase": "reveal"})
    )
    db.commit()
    if claimed == 0:
        return None

    # Round réellement clôturé par CET appel : si un minuteur est encore en
    # vol pour cette partie, l'annuler tout de suite plutôt que de le
    # laisser dormir pour rien jusqu'à `ROUND_GUESS_SECONDS` (revue de code
    # — voir le commentaire de `_round_timer_tasks`).
    _cancel_round_timer(game.id)

    # Pas de `db.refresh(game)` ici (revue de code) : les deux appelants ont
    # déjà un `game.current_track_id` à jour avant d'entrer dans cette
    # fonction (refresh explicite juste avant dans `_handle_guess_submitted`,
    # lecture fraîche dans `_round_timer`), et ce champ ne change jamais tant
    # que `round_started` — un second aller-retour DB ici n'apporterait rien
    # et ajoute une fenêtre de contention inutile avec l'autre session sur
    # la même connexion (StaticPool des tests).
    if game.mode == CLASSIC_MODE:
        return _close_classic_round(game, game_code)

    owner_pseudos = _resolve_owner_pseudos(db, game)

    # Union des joueurs actuellement présents et de ceux ayant une devinette
    # stockée pour ce round (revue de code) : un joueur qui a soumis une
    # devinette valide puis s'est déconnecté avant la clôture doit tout de
    # même être scoré — seule la vérification "tous ont répondu" de
    # `_handle_guess_submitted` doit se limiter aux joueurs actuellement
    # présents (un non-répondant déconnecté ne doit plus bloquer la
    # clôture).
    scoreable_pseudos = set(connection_manager.players(game_code)) | guess_store.known_pseudos(game.id)

    # Story 5 (spec-blindtest-integration-ui) : différentiel de CE round par
    # joueur, distinct du score cumulatif déjà renvoyé — jusqu'ici calculé
    # puis jeté, jamais diffusé au client (utile pour une animation de fin de
    # manche, nice-to-have CAP-4).
    deltas: dict[str, int] = {}

    for pseudo in scoreable_pseudos:
        if pseudo in owner_pseudos:
            # Retour utilisateur (2026-09-13) : le propriétaire marque
            # désormais un point fixe (OWNER_ROUND_BONUS) sur son propre
            # round, peu importe si les autres devinent juste ou pas —
            # avant, il était seulement garanti présent dans le snapshot via
            # un delta à 0, jamais scoré.
            score_store.add(game.id, pseudo, OWNER_ROUND_BONUS)
            deltas[pseudo] = OWNER_ROUND_BONUS
            continue

        # Retour utilisateur (2026-09-14) : "2 points par bonne réponse, 1
        # point retiré par mauvaise" — une réponse correcte accompagnée
        # d'autres noms cochés par prudence (ex. owner + un nom en plus) ne
        # doit PAS voir son +2 rogné par le malus des noms en trop : trouver
        # le bon propriétaire rapporte +2 plein, point. Le malus -1/nom ne
        # s'applique que si le propriétaire n'a PAS été trouvé (chaque nom
        # incorrect coché compte alors pour -1, cumulable — cf. tests
        # `test_owner_missed_wrong_names_nets_negative_no_floor`). Avec
        # plusieurs propriétaires, chacun trouvé rapporte +2.
        guess = guess_store.get_guess(game.id, pseudo) or []
        owners_found = sum(1 for name in guess if name in owner_pseudos)
        if owners_found:
            delta = 2 * owners_found
        else:
            delta = -len(guess)
        score_store.add(game.id, pseudo, delta)
        deltas[pseudo] = delta

    return {
        "owner_pseudo": owner_pseudos[0] if owner_pseudos else None,
        "owner_pseudos": owner_pseudos,
        "scores": score_store.snapshot(game.id),
        "deltas": deltas,
    }


def _schedule_round_timer(game_id: int, game_code: str, track_id: int) -> None:
    """Démarre la tâche de fond `_round_timer` pour ce round et l'enregistre
    dans `_round_timer_tasks` (Story 2.6, extrait en Story 2.7 pour être
    appelé aussi bien après le premier round (`start_game`) qu'après chaque
    round suivant tiré par `_advance_round`) — logique inchangée, juste
    nommée et partagée entre les deux points d'appel."""
    timer_task = asyncio.create_task(_round_timer(game_id, game_code, track_id))
    _round_timer_tasks[game_id] = timer_task
    timer_task.add_done_callback(
        lambda t, gid=game_id: (
            _round_timer_tasks.pop(gid, None)
            if _round_timer_tasks.get(gid) is t
            else None
        )
    )


async def _round_timer(game_id: int, game_code: str, track_id: int) -> None:
    """Minuteur serveur (Story 2.6) : clôture le round après
    `ROUND_GUESS_SECONDS` si personne ne l'a déjà fait via la clôture
    anticipée de `_handle_guess_submitted`. Tâche de fond démarrée juste
    après un `start_game` réussi — ne peut pas réutiliser la session DB
    scopée à une requête/connexion WS (celle-ci peut fermer avant que le
    minuteur ne se déclenche), d'où sa propre `SessionLocal()` ouverte et
    fermée entièrement ici (cf. Design Notes de la spec)."""
    await asyncio.sleep(ROUND_GUESS_SECONDS)

    db = SessionLocal()
    try:
        game = db.query(Game).filter(Game.id == game_id).first()
        if game is None or game.phase != "round_started" or game.current_track_id != track_id:
            # Défense en profondeur en plus du guard de phase dans
            # `_close_round` : un round déjà clôturé par ailleurs (clôture
            # anticipée, ou même déjà avancé vers un round suivant par
            # `_advance_round`, Story 2.7) rend ce minuteur périmé un no-op.
            return
        await _close_round_and_advance(db, game, game_code)
    except Exception:
        # Tâche de fond détachée : rien d'autre n'observe une exception levée
        # ici, on se contente de la journaliser.
        logger.exception("Erreur dans le minuteur de round (game_id=%s)", game_id)
    finally:
        db.close()


# Story 2.7 (revue de code) : même rationale que `_round_timer_tasks` pour
# `_advance_round` — référence forte requise pour éviter le ramassage GC
# prématuré d'une tâche non autrement référencée par l'event loop.
_advance_round_tasks: dict = {}


def _schedule_advance_round(game_id: int, game_code: str, delay: Optional[float] = None) -> None:
    """Démarre `_advance_round` en tâche de fond détachée (Story 2.7, revue
    de code) et l'enregistre dans `_advance_round_tasks` — mirroir exact de
    `_schedule_round_timer`/`_round_timer_tasks`. Nécessaire car
    `_advance_round` dort `REVEAL_DISPLAY_SECONDS` : exécutée inline dans la
    boucle de réception WS du joueur qui a clôturé le round (comme c'était le
    cas avant cette revue), elle bloquerait cette connexion — traitement des
    messages suivants, détection de déconnexion — pendant toute la durée du
    sommeil."""
    task = asyncio.create_task(_advance_round(game_id, game_code, delay))
    _advance_round_tasks[game_id] = task
    task.add_done_callback(
        lambda t, gid=game_id: (
            _advance_round_tasks.pop(gid, None)
            if _advance_round_tasks.get(gid) is t
            else None
        )
    )


async def _advance_round(game_id: int, game_code: str, delay: Optional[float] = None) -> None:
    """Enchaînement automatique serveur après un `reveal` (Story 2.7) :
    laisse le reveal affiché `REVEAL_DISPLAY_SECONDS`, puis tire soit le
    round suivant (`game_state {phase: next_round}` puis `round_started`),
    soit termine la partie (`game_state {phase: ended, final_scores}`) —
    selon que `ROUNDS_PER_GAME` est atteint ou que le pot n'a plus de
    morceau éligible non-encore-tiré.

    Tâche de fond détachée (revue de code, `_schedule_advance_round`) : ne
    peut pas réutiliser la session DB de son appelant (`_close_round_and_advance`,
    lui-même appelé depuis la boucle de réception WS d'un joueur ou depuis
    `_round_timer` — l'une ou l'autre peut fermer avant que ce sommeil ne se
    termine), d'où sa propre `SessionLocal()` ouverte et fermée entièrement
    ici, même mirroir que `_round_timer`.

    Re-vérifie `game.phase == "reveal"` après le sommeil (défense en
    profondeur, mirroir du guard de `_round_timer`) : appelée uniquement par
    `_close_round_and_advance` après que CET appel a effectivement gagné la
    revendication atomique de `_close_round` (jamais depuis le chemin
    perdant), donc ce guard ne devrait normalement jamais se déclencher — il
    reste néanmoins la même défense en profondeur que le reste de ce
    module.

    `delay` remplace `REVEAL_DISPLAY_SECONDS` quand il n'y a pas de reveal à
    laisser affiché (round annulé)."""
    await asyncio.sleep(REVEAL_DISPLAY_SECONDS if delay is None else delay)

    db = SessionLocal()
    try:
        game = db.query(Game).filter(Game.id == game_id).first()
        if game is None or game.phase != "reveal":
            return

        # Vérification bon marché (comptage en mémoire) avant toute requête
        # DB de tirage, dans cet ordre précis (cf. Boundaries de la spec) :
        # la limite de rounds coupe court sans même consulter le pot restant.
        track: Optional[Track] = None
        if played_tracks_store.count(game.id) < _get_rounds_target(game.id):
            track = _draw_eligible_track(db, game)

            # Story 8 (revue de code) : `None` ici peut vouloir dire soit un
            # pot réellement épuisé, soit des morceaux non-joués existants
            # mais dont les propriétaires sont momentanément déconnectés
            # (reload de page, coupure réseau brève) -- `_has_unplayed_track`
            # distingue les deux. Fenêtre de grâce bornée avant de traiter le
            # second cas comme définitif, pour ne pas terminer la partie sur
            # un simple aller-retour de connexion.
            attempt = 0
            while track is None and attempt < TRACK_POOL_RETRY_ATTEMPTS and _has_unplayed_track(db, game):
                await asyncio.sleep(TRACK_POOL_RETRY_DELAY_SECONDS)
                db.refresh(game)
                if game.phase != "reveal":
                    # Un autre chemin a déjà fait avancer la partie pendant
                    # l'attente (défense en profondeur, même garde qu'à
                    # l'entrée de cette fonction) -- rien de plus à faire ici.
                    return
                track = _draw_eligible_track(db, game)
                attempt += 1

        if track is None:
            game.phase = "ended"
            db.commit()
            # `final_scores` (Story 2.7, classement terminal) et `scores`
            # (Story 4, `game_id=` ci-dessous) portent volontairement le même
            # contenu ici : `final_scores` reste le contrat existant/testé
            # pour l'écran `ended`, `scores` est le contrat générique ajouté
            # par Story 4 pour le scoreboard permanent des autres phases —
            # aucune divergence possible, les deux lisent `score_store.snapshot`.
            await connection_manager.broadcast_game_state(
                game_code,
                {**_game_state_extra(game), "final_scores": score_store.snapshot(game.id)},
                game_id=game.id,
            )
            return

        # `game_state {phase: next_round}` annonce la transition avant le
        # tirage effectif du round suivant (`round_started`) — laisse le
        # temps au client d'afficher un indicateur "round suivant..." (cf.
        # Code Map).
        await connection_manager.broadcast_game_state(
            game_code, {**_game_state_extra(game), "phase": "next_round"}, game_id=game.id
        )

        start_seconds = _pick_start_seconds(track.duration_seconds)

        game.phase = "round_started"
        game.current_track_id = track.id
        db.commit()

        # Retour utilisateur (2026-09-14) : par `youtube_video_id`, pas
        # `track.id` — cf. `_draw_eligible_track`.
        played_tracks_store.add(game.id, track.youtube_video_id)
        guess_store.reset_round(game.id)

        # Critique (revue de code) : le client ne met à jour `phase` que via
        # `game_state` (`onGameState`) — `onRoundStarted` ne pousse que le
        # morceau, jamais la phase. Sans ce `game_state` explicite, `phase`
        # restait bloqué à "next_round" côté client après le round 1 (la
        # branche de rendu "round suivant..." l'emportant alors pour de bon
        # sur celle de la devinette), rendant la partie injouable au-delà du
        # premier round.
        await connection_manager.broadcast_game_state(
            game_code, _game_state_extra(game), game_id=game.id
        )
        await connection_manager.broadcast(game_code, "round_started", _round_payload(game, track, start_seconds))
        _schedule_round_timer(game.id, game_code, track.id)
    except Exception:
        # Tâche de fond détachée : rien d'autre n'observe une exception levée
        # ici, on se contente de la journaliser (mirroir de `_round_timer`).
        logger.exception("Erreur dans l'enchaînement automatique de round (game_id=%s)", game_id)
    finally:
        db.close()


async def _close_round_and_advance(db: Session, game: Game, game_code: str) -> None:
    """Clôture le round en cours puis enchaîne (Story 2.7) : point d'appel
    unique partagé par les deux chemins de clôture (`_handle_guess_submitted`
    et `_round_timer`), remplaçant leur ancien "appelle `_close_round`,
    diffuse `reveal`" dupliqué.

    Si `_close_round` renvoie `None` (revendication atomique perdue — l'autre
    chemin a déjà clôturé ce round), ne PAS enchaîner sur `_advance_round`
    ici : l'appelant gagnant le fait déjà de son côté, et `_advance_round`
    n'a pas elle-même de revendication atomique équivalente à celle de
    `_close_round` (son guard `phase != "reveal"` après le sommeil est un
    check-then-act, la même classe de race que celle documentée et corrigée
    sur `_close_round`). Appeler `_advance_round` depuis les deux chemins
    romprait l'invariant déjà documenté sur `_round_timer` ("un minuteur qui
    se déclenche après une clôture anticipée est inoffensif") en faisant
    tirer/terminer la partie deux fois en parallèle.

    `_advance_round` est démarrée en tâche de fond détachée
    (`_schedule_advance_round`, revue de code) plutôt qu'attendue ici : cette
    fonction tourne dans la boucle de réception WS du joueur dont le message
    a clôturé le round (via `_handle_guess_submitted`) ou dans la tâche de
    fond déjà détachée `_round_timer` — dans le premier cas, un `await`
    inline bloquerait ce joueur (traitement des messages suivants, détection
    de déconnexion) pendant toute `REVEAL_DISPLAY_SECONDS`."""
    payload = _close_round(db, game, game_code)
    if payload is None:
        return
    await connection_manager.broadcast(game_code, "reveal", payload)
    _schedule_advance_round(game.id, game_code)


async def _handle_guess_submitted(db: Session, game: Game, pseudo: str, payload: dict, game_code: str) -> None:
    """Traite un message `guess_submitted` (Story 2.5) : vérifie la phase et
    la validité de la sélection, puis enregistre la devinette en mémoire
    (`guess_store`). Un no-op silencieux sur tout échec de validation (même
    convention que `_handle_start_game`, cf. matrice I/O de la spec) : phase
    incorrecte, sélection vide/absente, ou tout pseudo listé qui n'est pas
    actuellement présent dans cette partie (rejet total de la soumission,
    pas d'application partielle).

    Story 2.6 : après un enregistrement réussi, vérifie la clôture anticipée
    — si tous les joueurs présents non-propriétaires ont désormais une
    devinette stockée, clôture le round.

    Story 2.7 : devient `async` (tourne déjà dans le handler WS async, un
    `await` supplémentaire est sans risque) et appelle désormais
    `_close_round_and_advance` directement au lieu de renvoyer un payload
    `reveal` à diffuser par l'appelant — la diffusion du `reveal` ET
    l'enchaînement automatique du round suivant vivent maintenant dans cette
    fonction partagée."""
    db.refresh(game)
    if game.phase != "round_started":
        return

    # Une devinette est liée au round dans lequel elle a été faite : le client
    # renvoie le `trackId` reçu dans `round_started`. Une devinette retardée
    # par le réseau qui arrive après l'enchaînement automatique du round
    # suivant porte l'id de l'ancien morceau et est ignorée (no-op silencieux,
    # comme toute autre validation). `bool` est exclu explicitement car c'est
    # une sous-classe de `int` en Python.
    track_id = payload.get("track_id") if isinstance(payload, dict) else None
    if not isinstance(track_id, int) or isinstance(track_id, bool):
        return
    if track_id != game.current_track_id:
        return

    target_player_ids = payload.get("target_player_ids") if isinstance(payload, dict) else None
    if not isinstance(target_player_ids, list) or not target_player_ids:
        return
    if not all(isinstance(pid, str) for pid in target_player_ids):
        return

    present_players = set(connection_manager.players(game_code))
    if not all(pid in present_players for pid in target_player_ids):
        return

    # Dédoublonne en préservant l'ordre : un pseudo répété (`["Bob","Bob"]`)
    # ne doit pas être compté plusieurs fois par la règle de score
    # -1/nom-incorrect de Story 2.6 (revue de code).
    target_player_ids = list(dict.fromkeys(target_player_ids))

    guess_store.submit(game.id, pseudo, target_player_ids)

    # Retour utilisateur (2026-09-14) : "les rounds doivent toujours durer 30
    # secondes" — la clôture anticipée dès que tous les joueurs présents
    # avaient répondu (Story 2.6) est retirée : un round ne se clôture plus
    # désormais que via `_round_timer` après `ROUND_GUESS_SECONDS`, jamais
    # avant, même si tout le monde a déjà soumis sa devinette. Enregistrer la
    # devinette (ci-dessus) reste utile immédiatement : elle sera scorée
    # normalement à la clôture par le minuteur.


def _current_classic_round(db: Session, game: Game, payload: Optional[dict]):
    """Le round classique visé par un message client, ou `None` s'il n'est plus
    d'actualité : mauvais mode, round clos, ou `track_id` d'un round passé."""
    db.refresh(game)
    if game.mode != CLASSIC_MODE or game.phase != "round_started":
        return None
    track_id = payload.get("track_id") if isinstance(payload, dict) else None
    if not isinstance(track_id, int) or isinstance(track_id, bool):
        return None
    current = classic_round_store.get(game.id)
    if current is None or track_id != game.current_track_id or track_id != current.track_id:
        return None
    return current


async def _handle_answer_submitted(db: Session, game: Game, pseudo: str, payload: dict, game_code: str) -> None:
    """Juge une réponse tapée. Le texte est la seule donnée lue : le verdict et
    le temps sont calculés ici, jamais reçus du client. `answer_result` est
    privé et ne dit que ce qui est trouvé, pas ce qu'il fallait répondre.

    Un round fermé, un élément déjà trouvé ou un texte invalide ne donnent lieu
    à aucune réponse (no-op silencieux, cf. matrice I/O)."""
    current = _current_classic_round(db, game, payload)
    if current is None:
        return
    text = payload.get("text")
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_ANSWER_CHARS:
        return

    already_found = current.found_by(pseudo)
    added = classic.match_answer(text, current.reference, skip=already_found)
    if not added and classic.match_answer(text, current.reference):
        return

    points_before = _classic_round_points(already_found)
    current.record(pseudo, added)
    finds = current.found_by(pseudo)
    gained = _classic_round_points(finds) - points_before
    # Avant tout `await` : le score ne doit pas pouvoir manquer au reveal.
    score_store.add(game.id, pseudo, gained)

    await connection_manager.send_to(
        game_code,
        pseudo,
        "answer_result",
        {"track_id": current.track_id, "added": sorted(added), "found": sorted(finds), "points": gained},
    )
    if added:
        await connection_manager.broadcast(game_code, "scores_updated", {"scores": score_store.snapshot(game.id)})


async def _handle_video_error(db: Session, game: Game, pseudo: str, payload: dict, game_code: str) -> None:
    """Un joueur signale que la vidéo ne se lance pas. Dès que la moitié des
    joueurs connectés l'a signalé, le round est annulé : les points déjà marqués
    sont retirés et le morceau reste écarté, mais le round ne compte pas."""
    current = _current_classic_round(db, game, payload)
    if current is None:
        return
    current.video_errors.add(pseudo)
    connected = set(connection_manager.players(game_code))
    if len(current.video_errors & connected) * 2 < len(connected):
        return

    # Même verrou que `_close_round` : un seul appelant clôt le round.
    claimed = (
        db.query(Game)
        .filter(Game.id == game.id, Game.phase == "round_started")
        .update({"phase": "reveal"})
    )
    db.commit()
    if claimed == 0:
        return
    _cancel_round_timer(game.id)

    voided = classic_round_store.finish(game.id)
    for player, finds in voided.finds.items():
        score_store.add(game.id, player, -_classic_round_points(finds))
    _rounds_target[game.id] = _get_rounds_target(game.id) + 1

    code = payload.get("code")
    logger.warning(
        "Round classique annulé (code=%s) : vidéo %s, erreur IFrame %s",
        game_code, voided.payload["videoId"], code if isinstance(code, int) else None,
    )

    await connection_manager.broadcast(game_code, "round_voided", {"scores": score_store.snapshot(game.id)})
    _schedule_advance_round(game.id, game_code, VOIDED_ROUND_DELAY_SECONDS)


async def _send_classic_round_to_joiner(game: Game, game_code: str, pseudo: str) -> None:
    """Un joueur qui arrive ou recharge la page en plein round reprend la
    musique au bon endroit et retrouve ce qu'il avait déjà trouvé."""
    current = classic_round_store.get(game.id)
    if current is None:
        return
    elapsed = current.elapsed()
    await connection_manager.send_to(
        game_code,
        pseudo,
        "round_started",
        {
            **current.payload,
            "startSeconds": current.payload["startSeconds"] + int(elapsed),
            "elapsedSeconds": elapsed,
        },
    )
    found = sorted(current.found_by(pseudo))
    if found:
        await connection_manager.send_to(
            game_code,
            pseudo,
            "answer_result",
            {"track_id": current.track_id, "added": [], "found": found, "points": 0, "restored": True},
        )


@game_router.websocket("/blindtest/games/{code}/ws")
async def game_lobby_ws(websocket: WebSocket, code: str, db: Session = Depends(get_db)):
    """Canal WS de lobby : `join {pseudo}` -> diffusion `game_state
    {players}` à tous les sockets connectés de cette partie.

    Le code de partie est validé (existence, insensible à la casse) avant
    d'accepter la poignée de main — un code inconnu ferme la connexion sans
    jamais l'accepter (cf. matrice I/O). Toute la présence est dérivée des
    sockets ouverts, indexée par le code normalisé en majuscules."""
    game_code = code.upper()
    game = db.query(Game).filter(Game.code == game_code).first()
    if not game:
        # Accepter la poignée de main avant de fermer est nécessaire même
        # dans ce cas : un `close()` envoyé avant que le handshake ASGI soit
        # terminé n'atteint jamais un vrai client comme frame de fermeture
        # portant ce code — uvicorn rejette la poignée de main avec un
        # simple 403 HTTP et jette le code. `TestClient` (transport ASGI
        # in-process) ne reproduit pas ce comportement, d'où le test
        # existant qui passait malgré ce bug sur le vrai fil. On aligne ce
        # chemin sur les deux autres (pseudo invalide/dupliqué) qui
        # accept-puis-close déjà.
        await websocket.accept()
        await websocket.close(code=WS_CLOSE_UNKNOWN_GAME, reason="Partie introuvable")
        return

    await websocket.accept()

    pseudo: str | None = None
    try:
        # Le premier message attendu est le `join` — tout le reste du cycle
        # de vie (déconnexion, broadcast) ne démarre qu'une fois un pseudo
        # valide et non déjà pris établi pour ce socket.
        try:
            raw = await websocket.receive_json()
        except ValueError:
            await websocket.close(code=WS_CLOSE_INVALID_PSEUDO, reason="Message invalide")
            return

        if not isinstance(raw, dict) or raw.get("type") != "join":
            await websocket.close(code=WS_CLOSE_INVALID_PSEUDO, reason="Pseudo invalide")
            return

        payload = raw.get("payload") if isinstance(raw, dict) else None
        candidate = payload.get("pseudo") if isinstance(payload, dict) else None
        candidate = candidate.strip() if isinstance(candidate, str) else ""

        if not candidate or len(candidate) > MAX_PSEUDO_LENGTH:
            await websocket.close(code=WS_CLOSE_INVALID_PSEUDO, reason="Pseudo invalide")
            return
        if connection_manager.has_pseudo(game_code, candidate):
            await websocket.close(code=WS_CLOSE_DUPLICATE_PSEUDO, reason="Pseudo déjà utilisé dans cette partie")
            return

        pseudo = candidate
        connection_manager.connect(game_code, pseudo, websocket)

        # Story 2.4 : le premier pseudo à rejoindre le lobby d'une partie
        # fraîchement créée en devient l'hôte — assigné une seule fois,
        # jamais réassigné ensuite (colonne DB, survit à une reconnexion
        # sous le même pseudo).
        if game.host_pseudo is None:
            game.host_pseudo = pseudo
            db.commit()

        # Story 2.7 : un (re)joignant qui arrive alors que la partie est déjà
        # `ended` doit voir le classement final tout de suite — seul écart
        # "late joiner" que cette story ferme (cf. Boundaries de la spec) :
        # `ended` est un état terminal permanent, contrairement à
        # `round_started`/`reveal` qui restent sans rejeu pour un (re)joignant
        # (limitation acceptée, inchangée).
        join_state_extra = _game_state_extra(game)
        if game.phase == "ended":
            join_state_extra["final_scores"] = score_store.snapshot(game.id)
        elif game.phase == "round_started" and game.current_track_id is not None:
            # Un joignant en cours de round doit pouvoir deviner : il reçoit
            # l'id du round en cours à renvoyer dans `guess_submitted`.
            join_state_extra["track_id"] = game.current_track_id

        await connection_manager.broadcast_game_state(game_code, join_state_extra, game_id=game.id)
        if game.mode == CLASSIC_MODE and game.phase == "round_started":
            await _send_classic_round_to_joiner(game, game_code, pseudo)

        while True:
            try:
                raw = await websocket.receive_json()
            except ValueError:
                await websocket.close(code=WS_CLOSE_INVALID_PSEUDO, reason="Message invalide")
                return

            # Story 2.4 : dispatch sur le type de message. Tout ce qui n'est
            # pas `start_game` garde le comportement tolérant no-op de la
            # Story 2.1 (pas d'autre message client->serveur avant 2.5).
            if isinstance(raw, dict) and raw.get("type") == "start_game":
                refusal = _classic_start_refusal(db, game, pseudo, raw.get("payload"))
                if refusal is not None:
                    await connection_manager.send_to(game_code, pseudo, "start_refused", refusal)
                    continue
                round_payload = _handle_start_game(db, game, pseudo, raw.get("payload"))
                if round_payload is not None:
                    # Critique (revue de code, Story 2.7) : le client ne met
                    # à jour `phase` que via `game_state` (`onGameState`) —
                    # `round_started` (`onRoundStarted`) ne pousse que le
                    # morceau, jamais la phase. Ce `game_state` manquait déjà
                    # ici avant Story 2.7 (round 1), mais ça ne se voyait pas
                    # tant qu'aucun round suivant n'existait ; désormais requis
                    # pour que l'UI de devinette apparaisse à chaque round.
                    await connection_manager.broadcast_game_state(
                        game_code, _game_state_extra(game), game_id=game.id
                    )
                    await connection_manager.broadcast(game_code, "round_started", round_payload)
                    # Story 2.6 : minuteur de clôture démarré en tâche de
                    # fond juste après un tirage réussi — sa propre session
                    # DB (`SessionLocal`), indépendante de celle de cette
                    # connexion WS qui peut fermer avant qu'il ne se
                    # déclenche (cf. Design Notes de la spec). Story 2.7 :
                    # extrait dans `_schedule_round_timer`, partagé avec
                    # l'enchaînement automatique des rounds suivants.
                    _schedule_round_timer(game.id, game_code, game.current_track_id)
            elif isinstance(raw, dict) and raw.get("type") == "guess_submitted":
                # Story 2.5 : aucune diffusion pour l'enregistrement de la
                # devinette elle-même — Story 2.6/2.7 : si cette soumission
                # clôture le round (tous les joueurs présents non-
                # propriétaires ont répondu), `_handle_guess_submitted`
                # diffuse elle-même le `reveal` puis enchaîne (round suivant
                # ou fin de partie) via `_close_round_and_advance`.
                await _handle_guess_submitted(db, game, pseudo, raw.get("payload"), game_code)
            elif isinstance(raw, dict) and raw.get("type") == "answer_submitted":
                await _handle_answer_submitted(db, game, pseudo, raw.get("payload"), game_code)
            elif isinstance(raw, dict) and raw.get("type") == "video_error":
                await _handle_video_error(db, game, pseudo, raw.get("payload"), game_code)
            elif isinstance(raw, dict) and raw.get("type") == "restart_game":
                # Retour utilisateur (2026-09-14) : "rejouer dans le même
                # salon" — mêmes joueurs/playlists, nouveau `game_state
                # {phase: lobby}` diffusé à tous pour réafficher l'écran de
                # lobby (dont le bouton "Démarrer la partie" pour l'hôte).
                if _handle_restart_game(db, game, pseudo):
                    await connection_manager.broadcast_game_state(
                        game_code, _game_state_extra(game), game_id=game.id
                    )
    except WebSocketDisconnect:
        pass
    finally:
        if pseudo is not None:
            connection_manager.disconnect(game_code, pseudo)
            # Re-lire l'état DB avant de diffuser : une autre connexion a pu
            # démarrer le round entre-temps (`start_game`), et broadcaster
            # l'objet `game` chargé à la connexion (jamais rafraîchi depuis)
            # renverrait un `phase: "lobby"` périmé à tous les clients
            # restants (revue de code).
            db.refresh(game)

            # Story 7 (spec-blindtest-integration-ui) : si l'hôte qui vient de
            # partir était game.host_pseudo, transférer le statut au premier
            # joueur encore connecté plutôt que de laisser la partie bloquée
            # sans personne habilité à déclencher `start_game`. Rien à
            # réassigner si plus personne n'est présent — la partie reste
            # simplement abandonnée. `players()` reflète l'ordre d'ARRIVÉE
            # ORIGINAL dans le dict (un rejoin ne fait que réécrire la valeur
            # d'une clé existante, sans la déplacer) : "premier encore
            # connecté" veut dire premier arrivé historiquement, pas premier
            # reconnecté.
            remaining_players = connection_manager.players(game_code)
            if pseudo == game.host_pseudo and remaining_players:
                new_host = remaining_players[0]
                game.host_pseudo = new_host
                db.commit()
                logger.info(
                    "Hôte réassigné après déconnexion (game_id=%s, code=%s): %s -> %s",
                    game.id, game_code, pseudo, new_host,
                )

            await connection_manager.broadcast_game_state(
                game_code, _game_state_extra(game), game_id=game.id
            )
