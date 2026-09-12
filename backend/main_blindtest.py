"""Router du module blindtest — import de playlist publique (Epic 1, Story
1.1) et lobby/connexion temps réel (Epic 2, Story 2.1). Mirroir de
`main_games.py` pour la forme (APIRouter, Depends(get_db), limiter) mais
branché sur la DB isolée `app.blindtest.database` (AD-7).
"""
import logging
import random
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.auth import require_admin_session
from app.blindtest import cache, matching, schemas
from app.blindtest.database import get_db
from app.blindtest.errors import PrivatePlaylistError, ProviderConfigError, UnrecognizedUrlError
from app.blindtest.game_connections import guess_store
from app.blindtest.game_connections import manager as connection_manager
from app.blindtest.import_pipeline import extract_tracks
from app.blindtest.models import Game, Playlist, Track
from app.game_helpers import generate_session_code
from app.rate_limit import limiter

logger = logging.getLogger(__name__)

router = APIRouter()

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

    eligible_tracks = (
        db.query(Track)
        .join(Playlist, Track.playlist_id == Playlist.id)
        .filter(
            Playlist.game_id == game.id,
            Track.youtube_video_id.isnot(None),
            Track.duration_seconds.isnot(None),
            Track.duration_seconds > 0,
        )
        .all()
    )
    if not eligible_tracks:
        return None

    track = random.choice(eligible_tracks)
    start_seconds = random.randint(0, track.duration_seconds - 1)

    game.phase = "round_started"
    game.current_track_id = track.id
    db.commit()

    # Story 2.5 : un nouveau round tiré invalide toute devinette encore en
    # mémoire pour le round précédent — sans ça, une devinette non
    # resoumise par un joueur silencieux survivrait au changement de round
    # et serait scorée à tort par Story 2.6/2.7 (Boundaries de la spec).
    guess_store.reset_round(game.id)

    return {"videoId": track.youtube_video_id, "startSeconds": start_seconds}


def _handle_guess_submitted(db: Session, game: Game, pseudo: str, payload: dict, game_code: str) -> None:
    """Traite un message `guess_submitted` (Story 2.5) : vérifie la phase et
    la validité de la sélection, puis enregistre la devinette en mémoire
    (`guess_store`). Aucune diffusion, aucune réponse — un no-op silencieux
    sur tout échec de validation (même convention que `_handle_start_game`,
    cf. matrice I/O de la spec) : phase incorrecte, sélection vide/absente,
    ou tout pseudo listé qui n'est pas actuellement présent dans cette
    partie (rejet total de la soumission, pas d'application partielle)."""
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

        await connection_manager.broadcast_game_state(
            game_code, {"phase": game.phase, "host_pseudo": game.host_pseudo}
        )

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
                    await connection_manager.broadcast(game_code, "round_started", round_payload)
            elif isinstance(raw, dict) and raw.get("type") == "guess_submitted":
                # Story 2.5 : ni diffusion ni réponse — la devinette n'est
                # visible que côté serveur jusqu'au `reveal` de Story 2.6.
                _handle_guess_submitted(db, game, pseudo, raw.get("payload"), game_code)
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
