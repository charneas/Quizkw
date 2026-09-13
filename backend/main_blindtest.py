"""Router du module blindtest — import de playlist publique (Epic 1, Story
1.1) et lobby/connexion temps réel (Epic 2, Story 2.1). Mirroir de
`main_games.py` pour la forme (APIRouter, Depends(get_db), limiter) mais
branché sur la DB isolée `app.blindtest.database` (AD-7).
"""
import asyncio
import logging
import random
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.auth import require_admin_session
from app.blindtest import cache, matching, schemas
from app.blindtest.database import SessionLocal, get_db
from app.blindtest.errors import PrivatePlaylistError, ProviderConfigError, UnrecognizedUrlError
from app.blindtest.game_connections import guess_store, played_tracks_store, score_store
from app.blindtest.game_connections import manager as connection_manager
from app.blindtest.import_pipeline import extract_tracks
from app.blindtest.models import Game, Playlist, Track
from app.game_helpers import generate_session_code
from app.rate_limit import limiter

logger = logging.getLogger(__name__)

router = APIRouter()

# Story 2.6 : durée fixe (secondes) du minuteur serveur qui clôture un round
# si tous les joueurs présents non-propriétaires n'ont pas répondu avant.
# Module-level pour être monkeypatché par les tests (valeur réduite sur le
# chemin de test qui exerce réellement le timeout).
ROUND_GUESS_SECONDS = 30

# Story 2.7 : nombre de rounds joués avant fin de partie automatique, et
# durée (secondes) de la pause sur l'écran de reveal avant l'enchaînement
# automatique serveur vers le round suivant (ou la fin de partie). Toutes
# deux module-level pour être monkeypatchées par les tests, même convention
# que `ROUND_GUESS_SECONDS`.
ROUNDS_PER_GAME = 15
REVEAL_DISPLAY_SECONDS = 6

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


@router.post("/blindtest/playlists", response_model=schemas.PlaylistResponse, status_code=201)
@limiter.limit("10/minute")
def import_playlist(
    request: Request,
    body: schemas.PlaylistImportRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Extrait une playlist publique (Spotify/YouTube/Apple Music) et
    persiste `Playlist` + `Track`. Échec propre sans écriture partielle :
    l'extraction complète a lieu avant tout `db.add`/`db.commit`.

    Story 2.2 : `game_code`/`pseudo` scopent optionnellement l'import à une
    partie — validés avant toute extraction (échec rapide, pas d'appel
    provider inutile) puisqu'ils ne dépendent que de l'état DB/WS, jamais du
    contenu de la playlist."""
    game = _validate_scope(body, db)

    try:
        provider, extracted = extract_tracks(body.url)
    except UnrecognizedUrlError:
        raise HTTPException(status_code=400, detail="URL de playlist non reconnue")
    except PrivatePlaylistError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except ProviderConfigError as exc:
        logger.error("Configuration provider manquante: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc))

    # Re-vérification juste avant la persistance : `extract_tracks` est un
    # aller-retour réseau qui peut prendre plusieurs secondes, pendant
    # lesquelles la partie peut quitter la phase `lobby` ou le pseudo se
    # déconnecter. Sans ce second contrôle, la playlist serait tout de même
    # committée et scopée à un game/pseudo devenu obsolète (revue de code).
    game = _validate_scope(body, db)

    playlist = Playlist(
        source_url=body.url,
        provider=provider,
        game_id=game.id if game else None,
        owner_pseudo=body.pseudo if game else None,
    )
    db.add(playlist)
    db.flush()  # obtenir playlist.id pour les FK des tracks, avant commit

    for item in extracted:
        db.add(Track(
            playlist_id=playlist.id,
            title=item.title,
            artist=item.artist,
            isrc=item.isrc,
            youtube_video_id=item.youtube_video_id,
            source_url=item.source_url,
        ))
        if item.youtube_video_id:
            # Import direct YouTube : le morceau est déjà résolu, on
            # alimente le cache tout de suite pour qu'un futur import
            # Spotify/Apple Music du même morceau tape le cache (Story 1.3).
            # `duration_seconds=None` explicite (Story 2.3) : la durée n'est
            # pas encore connue à ce stade synchrone — c'est
            # `match_playlist_tracks` (tâche de fond planifiée juste après)
            # qui la récupérera et la persistera, jamais cette requête
            # player-facing (NFR1).
            cache.store(db, item.isrc, item.title, item.artist, item.youtube_video_id, duration_seconds=None)

    db.commit()
    db.refresh(playlist)

    background_tasks.add_task(matching.match_playlist_tracks, playlist.id)

    return playlist


@router.get("/blindtest/playlists/{playlist_id}", response_model=schemas.PlaylistResponse)
def get_playlist(playlist_id: int, db: Session = Depends(get_db)):
    """Permet au client de poller l'état de résolution (matching en tâche de
    fond) d'une playlist déjà importée."""
    playlist = db.query(Playlist).filter(Playlist.id == playlist_id).first()
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist introuvable")
    return playlist


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
def create_game(request: Request, db: Session = Depends(get_db)):
    """Crée une partie de blind test avec un code unique à 6 caractères.

    Même boucle de génération-et-vérification de collision que
    `main_games.create_game`, mais contre la table `Game` isolée du module
    blindtest (jamais contre `GameSession` de la DB principale).

    La vérification préalable (`filter(Game.code == code).first()`) laisse
    une fenêtre de course entre deux requêtes concurrentes : la contrainte
    unique sur `code` reste le garde-fou final, donc l'insertion elle-même
    est protégée par une boucle de retry bornée sur `IntegrityError`."""
    for attempt in range(MAX_CODE_GENERATION_ATTEMPTS):
        code = generate_session_code()
        while db.query(Game).filter(Game.code == code).first():
            code = generate_session_code()

        game = Game(code=code, phase="lobby")
        db.add(game)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            continue
        db.refresh(game)
        return game

    raise HTTPException(status_code=500, detail="Impossible de générer un code de partie unique")


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
    plutôt que de compter sur SQLAlchemy pour bien la neutraliser."""
    query = (
        db.query(Track)
        .join(Playlist, Track.playlist_id == Playlist.id)
        .filter(
            Playlist.game_id == game.id,
            Track.youtube_video_id.isnot(None),
            Track.duration_seconds.isnot(None),
            Track.duration_seconds > 0,
        )
    )
    played_ids = played_tracks_store.played_ids(game.id)
    if played_ids:
        query = query.filter(Track.id.notin_(played_ids))

    eligible_tracks = query.all()
    if not eligible_tracks:
        return None
    return random.choice(eligible_tracks)


def _handle_start_game(db: Session, game: Game, requesting_pseudo: str) -> Optional[dict]:
    """Traite un message `start_game` (Story 2.4) : vérifie hôte/phase, tire
    un morceau éligible du pot de cette partie, calcule un offset de départ
    aléatoire et fait passer la partie en `round_started`.

    Renvoie le payload `round_started {videoId, startSeconds}` à diffuser,
    ou `None` si une vérification échoue (non-hôte, phase déjà avancée, pot
    vide) — l'appelant ne diffuse alors rien (no-op silencieux, cf. matrice
    I/O : ni close, ni message d'erreur, ces cas sont défense-en-profondeur
    puisque le frontend ne montre le contrôle qu'à l'hôte)."""
    db.refresh(game)
    if requesting_pseudo != game.host_pseudo:
        return None
    if game.phase != "lobby":
        return None

    track = _draw_eligible_track(db, game)
    if track is None:
        return None

    start_seconds = random.randint(0, track.duration_seconds - 1)

    game.phase = "round_started"
    game.current_track_id = track.id
    db.commit()

    # Story 2.7 : ce premier round n'était jusqu'ici jamais enregistré dans
    # `played_tracks_store` (la story n'existait pas encore) — désormais
    # tout tirage, y compris le tout premier de la partie, y est enregistré
    # pour que l'exclusion et le compte de rounds joués s'appliquent
    # uniformément dès le round 1 (cf. Code Map de la spec).
    played_tracks_store.add(game.id, track.id)

    # Story 2.5 : un nouveau round tiré invalide toute devinette encore en
    # mémoire pour le round précédent — sans ça, une devinette non
    # resoumise par un joueur silencieux survivrait au changement de round
    # et serait scorée à tort par Story 2.6/2.7 (Boundaries de la spec).
    guess_store.reset_round(game.id)

    return {"videoId": track.youtube_video_id, "startSeconds": start_seconds}


def _resolve_owner_pseudo(db: Session, game: Game) -> Optional[str]:
    """Résout le vrai propriétaire du round en cours : `game.current_track_id`
    -> `Track` -> `Track.playlist_id` -> `Playlist.owner_pseudo`. `None` si
    `current_track_id` n'est pas renseigné (défensif, ne devrait pas arriver
    une fois `phase == "round_started"`)."""
    if game.current_track_id is None:
        return None
    track = db.query(Track).filter(Track.id == game.current_track_id).first()
    if track is None:
        return None
    playlist = db.query(Playlist).filter(Playlist.id == track.playlist_id).first()
    if playlist is None:
        return None
    return playlist.owner_pseudo


def _close_round(db: Session, game: Game, game_code: str) -> Optional[dict]:
    """Clôture le round en cours (Story 2.6) : calcule et cumule le score de
    chaque joueur présent non-propriétaire à partir de sa devinette stockée
    (`guess_store`), fait passer la partie en phase `reveal` et renvoie le
    payload `reveal {owner_pseudo, scores}` à diffuser.

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
    owner_pseudo = _resolve_owner_pseudo(db, game)

    # Union des joueurs actuellement présents et de ceux ayant une devinette
    # stockée pour ce round (revue de code) : un joueur qui a soumis une
    # devinette valide puis s'est déconnecté avant la clôture doit tout de
    # même être scoré — seule la vérification "tous ont répondu" de
    # `_handle_guess_submitted` doit se limiter aux joueurs actuellement
    # présents (un non-répondant déconnecté ne doit plus bloquer la
    # clôture).
    scoreable_pseudos = set(connection_manager.players(game_code)) | guess_store.known_pseudos(game.id)

    for pseudo in scoreable_pseudos:
        if pseudo == owner_pseudo:
            # Le propriétaire n'est pas scoré sur son propre round, mais on
            # garantit tout de même sa présence dans le snapshot (Boundaries
            # de la spec) via un ajout à delta 0.
            score_store.add(game.id, pseudo, 0)
            continue

        guess = guess_store.get_guess(game.id, pseudo) or []
        delta = 2 if owner_pseudo in guess else 0
        delta -= sum(1 for name in guess if name != owner_pseudo)
        score_store.add(game.id, pseudo, delta)

    return {"owner_pseudo": owner_pseudo, "scores": score_store.snapshot(game.id)}


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


def _schedule_advance_round(game_id: int, game_code: str) -> None:
    """Démarre `_advance_round` en tâche de fond détachée (Story 2.7, revue
    de code) et l'enregistre dans `_advance_round_tasks` — mirroir exact de
    `_schedule_round_timer`/`_round_timer_tasks`. Nécessaire car
    `_advance_round` dort `REVEAL_DISPLAY_SECONDS` : exécutée inline dans la
    boucle de réception WS du joueur qui a clôturé le round (comme c'était le
    cas avant cette revue), elle bloquerait cette connexion — traitement des
    messages suivants, détection de déconnexion — pendant toute la durée du
    sommeil."""
    task = asyncio.create_task(_advance_round(game_id, game_code))
    _advance_round_tasks[game_id] = task
    task.add_done_callback(
        lambda t, gid=game_id: (
            _advance_round_tasks.pop(gid, None)
            if _advance_round_tasks.get(gid) is t
            else None
        )
    )


async def _advance_round(game_id: int, game_code: str) -> None:
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
    module."""
    await asyncio.sleep(REVEAL_DISPLAY_SECONDS)

    db = SessionLocal()
    try:
        game = db.query(Game).filter(Game.id == game_id).first()
        if game is None or game.phase != "reveal":
            return

        # Vérification bon marché (comptage en mémoire) avant toute requête
        # DB de tirage, dans cet ordre précis (cf. Boundaries de la spec) :
        # la limite de rounds coupe court sans même consulter le pot restant.
        track: Optional[Track] = None
        if played_tracks_store.count(game.id) < ROUNDS_PER_GAME:
            track = _draw_eligible_track(db, game)

        if track is None:
            game.phase = "ended"
            db.commit()
            await connection_manager.broadcast_game_state(
                game_code,
                {
                    "phase": "ended",
                    "host_pseudo": game.host_pseudo,
                    "final_scores": score_store.snapshot(game.id),
                },
            )
            return

        # `game_state {phase: next_round}` annonce la transition avant le
        # tirage effectif du round suivant (`round_started`) — laisse le
        # temps au client d'afficher un indicateur "round suivant..." (cf.
        # Code Map).
        await connection_manager.broadcast_game_state(
            game_code, {"phase": "next_round", "host_pseudo": game.host_pseudo}
        )

        start_seconds = random.randint(0, track.duration_seconds - 1)

        game.phase = "round_started"
        game.current_track_id = track.id
        db.commit()

        played_tracks_store.add(game.id, track.id)
        guess_store.reset_round(game.id)

        # Critique (revue de code) : le client ne met à jour `phase` que via
        # `game_state` (`onGameState`) — `onRoundStarted` ne pousse que le
        # morceau, jamais la phase. Sans ce `game_state` explicite, `phase`
        # restait bloqué à "next_round" côté client après le round 1 (la
        # branche de rendu "round suivant..." l'emportant alors pour de bon
        # sur celle de la devinette), rendant la partie injouable au-delà du
        # premier round.
        await connection_manager.broadcast_game_state(
            game_code, {"phase": "round_started", "host_pseudo": game.host_pseudo}
        )
        await connection_manager.broadcast(
            game_code, "round_started", {"videoId": track.youtube_video_id, "startSeconds": start_seconds}
        )
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

    owner_pseudo = _resolve_owner_pseudo(db, game)
    non_owner_present = {p for p in present_players if p != owner_pseudo}
    if non_owner_present and non_owner_present.issubset(guess_store.known_pseudos(game.id)):
        await _close_round_and_advance(db, game, game_code)


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
        join_state_extra = {"phase": game.phase, "host_pseudo": game.host_pseudo}
        if game.phase == "ended":
            join_state_extra["final_scores"] = score_store.snapshot(game.id)

        await connection_manager.broadcast_game_state(game_code, join_state_extra)

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
                round_payload = _handle_start_game(db, game, pseudo)
                if round_payload is not None:
                    # Critique (revue de code, Story 2.7) : le client ne met
                    # à jour `phase` que via `game_state` (`onGameState`) —
                    # `round_started` (`onRoundStarted`) ne pousse que le
                    # morceau, jamais la phase. Ce `game_state` manquait déjà
                    # ici avant Story 2.7 (round 1), mais ça ne se voyait pas
                    # tant qu'aucun round suivant n'existait ; désormais requis
                    # pour que l'UI de devinette apparaisse à chaque round.
                    await connection_manager.broadcast_game_state(
                        game_code, {"phase": "round_started", "host_pseudo": game.host_pseudo}
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
            await connection_manager.broadcast_game_state(
                game_code, {"phase": game.phase, "host_pseudo": game.host_pseudo}
            )
