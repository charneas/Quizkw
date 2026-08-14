import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.memory_grid import MemoryGridManager, MemoryGrid, GridCell, MemoryGridRound, GridCellStatus, SuddenDeathRound
from app.game_helpers import require_host

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/games/{code}/memory-grid/create", response_model=schemas.MemoryGrid)
def create_memory_grid(code: str, db: Session = Depends(get_db), _host: models.GameSession = Depends(require_host)):
    """
    Créer une grille mémoire pour la manche 3 (7x5 grid)
    """
    game = db.query(models.GameSession).filter(models.GameSession.code == code).first()
    if not game:
        raise HTTPException(status_code=404, detail="Session de jeu non trouvée")

    # Vérifier que le jeu est à la manche 3
    if game.current_round != models.RoundType.MANCHE_3:
        raise HTTPException(status_code=400, detail="La grille mémoire est seulement disponible en manche 3")

    # Idempotence (reconnexion / rechargement de page) : une grille non
    # complétée existe déjà pour cette partie, on la retourne plutôt que
    # d'en recréer une (et de perdre la progression en cours).
    existing = db.query(MemoryGrid).filter(
        MemoryGrid.game_session_id == game.id,
        MemoryGrid.is_completed == False
    ).first()
    if existing:
        return existing

    manager = MemoryGridManager(db)
    memory_grid = manager.create_memory_grid(game.id, rows=5, cols=7)

    return memory_grid

@router.post("/games/{code}/memory-grid/start", response_model=schemas.StartMemoryGridRoundResponse)
def start_memory_grid_round(code: str, db: Session = Depends(get_db), _host: models.GameSession = Depends(require_host)):
    """
    Démarrer un tour de grille mémoire
    """
    game = db.query(models.GameSession).filter(models.GameSession.code == code).first()
    if not game:
        raise HTTPException(status_code=404, detail="Session de jeu non trouvée")

    # Vérifier qu'il y a une grille mémoire active
    memory_grid = db.query(MemoryGrid).filter(
        MemoryGrid.game_session_id == game.id,
        MemoryGrid.is_completed == False
    ).first()

    if not memory_grid:
        raise HTTPException(status_code=404, detail="Aucune grille mémoire active trouvée")

    # Idempotence (reconnexion / rechargement de page) : un round actif
    # existe déjà pour cette grille, on le retourne plutôt que d'en créer
    # un nouveau (qui réinitialiserait le joueur courant).
    existing_round = db.query(MemoryGridRound).filter(
        MemoryGridRound.memory_grid_id == memory_grid.id,
        MemoryGridRound.is_active == True
    ).first()
    if existing_round:
        return {
            "round_id": existing_round.id,
            "message": "Tour de grille mémoire déjà en cours"
        }

    manager = MemoryGridManager(db)
    round_obj = manager.start_memory_grid_round(game.id, memory_grid.id)

    return {
        "round_id": round_obj.id,
        "message": "Tour de grille mémoire démarré"
    }

@router.get("/memory-grid/{memory_grid_id}/state")
def get_memory_grid_state(memory_grid_id: int, db: Session = Depends(get_db)):
    """
    Obtenir l'état actuel de la grille mémoire
    """
    manager = MemoryGridManager(db)
    grid_state = manager.get_grid_state(memory_grid_id)

    if not grid_state:
        raise HTTPException(status_code=404, detail="Grille mémoire non trouvée")

    return grid_state

@router.post("/memory-grid/reveal-cell")
def reveal_cell(reveal_request: schemas.SelectCellRequest, db: Session = Depends(get_db)):
    """
    Révéler une cellule dans la grille mémoire
    """
    manager = MemoryGridManager(db)
    # AD-5 : l'endpoint possède la transaction. AD-6 : LookupError -> 404, ValueError -> 400.
    try:
        result = manager.reveal_cell(
            reveal_request.round_id, reveal_request.player_id, reveal_request.cell_id
        )
        db.commit()
    except LookupError as e:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

    return result

@router.post("/memory-grid/answer-cell")
def answer_cell(answer_request: schemas.AnswerCellRequest, db: Session = Depends(get_db)):
    """
    Répondre à une cellule révélée dans la grille mémoire.

    AD-3 : le corps porte la RÉPONSE du joueur, pas un verdict de correction.
    Le serveur compare lui-même à la bonne réponse.
    """
    manager = MemoryGridManager(db)
    try:
        result = manager.answer_cell(
            answer_request.round_id,
            answer_request.player_id,
            answer_request.cell_id,
            answer_request.player_answer,
        )
        # Une réponse (correcte ou non) clôt le tour du joueur courant : le
        # tour passe au finaliste suivant (tourniquet de advance_turn).
        manager.advance_turn(result["memory_grid_id"])
        manager.check_completion(result["memory_grid_id"])
        db.commit()
    except LookupError as e:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

    return result

@router.post("/memory-grid/{memory_grid_id}/skip-turn")
def skip_turn(memory_grid_id: int, expected_turn: int = None, db: Session = Depends(get_db)):
    """
    Fait passer la grille mémoire au tour suivant sans réponse à une cellule
    (déclenché par le timer de tour côté client quand il arrive à 0).

    C-003 : chaque client connecté fait tourner son propre timer et peut donc
    appeler ce endpoint indépendamment pour le même timeout. `expected_turn`
    (le tour observé par le client au moment où son timer a démarré) permet un
    compare-and-set : si le tour a déjà avancé depuis (réponse d'un joueur ou
    skip-turn d'un autre client), cet appel est ignoré au lieu de sauter un
    tour supplémentaire.
    """
    manager = MemoryGridManager(db)

    memory_grid = db.query(MemoryGrid).filter(MemoryGrid.id == memory_grid_id).first()
    if not memory_grid:
        raise HTTPException(status_code=404, detail="Memory grid not found")

    if expected_turn is not None and memory_grid.current_turn != expected_turn:
        return {"memory_grid_id": memory_grid_id, "current_turn": memory_grid.current_turn}

    # Playtest 2026-08-15 : une cellule dont le temps de réponse (60s) expire
    # est définitivement perdue — comme une mauvaise réponse — plutôt que
    # remise en jeu cachée : sinon elle pourrait être re-choisie plus tard
    # (par le même joueur ou un autre), ce qui n'a pas de sens pour une
    # question déjà "grillée". Personne ne la contrôle (answered_by_player_id
    # reste vide) : aucun point, aucune case comptée pour qui que ce soit.
    revealed_cell = db.query(GridCell).filter(
        GridCell.memory_grid_id == memory_grid_id,
        GridCell.status == GridCellStatus.REVEALED
    ).first()
    if revealed_cell:
        revealed_cell.status = GridCellStatus.ANSWERED

    new_turn = manager.advance_turn(memory_grid_id)
    manager.check_completion(memory_grid_id)
    db.commit()

    return {"memory_grid_id": memory_grid_id, "current_turn": new_turn}

@router.post("/games/{code}/advance-to-phase3")
def advance_to_phase3(code: str, db: Session = Depends(get_db), _host: models.GameSession = Depends(require_host)):
    """
    Pass to phase 3 (final round with memory grid)
    """
    game = db.query(models.GameSession).filter(models.GameSession.code == code).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game session not found")

    # Idempotent : plusieurs finalistes peuvent atterrir sur l'écran Manche 3
    # en même temps et déclencher cet appel simultanément (AD-7 : un rejeu ne
    # doit pas échouer). Vérifié AVANT le garde is_active : un rejeu après que
    # la partie a été désactivée (ex. fin de partie) reste un no-op réussi
    # plutôt qu'un faux "Game is not active" trompeur (trouvé en revue de code).
    if game.current_round == models.RoundType.MANCHE_3:
        return {
            "message": "La partie est déjà en Manche 3",
            "current_round": game.current_round.value
        }

    # Check if game is active and can proceed to phase 3
    if not game.is_active:
        logger.warning("advance_to_phase3 refusé pour %s : partie inactive", code)
        raise HTTPException(status_code=400, detail="Game is not active")

    # AD-7 : la transition part de la Manche 2 — un garde vérifie que la
    # manche précédente a réellement eu lieu avant de sauter en Manche 3.
    if game.current_round != models.RoundType.MANCHE_2:
        logger.warning(
            "advance_to_phase3 refusé pour %s : partie en %s, pas MANCHE_2",
            code, game.current_round.value,
        )
        raise HTTPException(
            status_code=400,
            detail=f"La Manche 3 ne peut démarrer qu'après la Manche 2 ; la partie est en {game.current_round.value}"
        )

    # Advance to round 3
    game.current_round = models.RoundType.MANCHE_3
    db.commit()
    logger.info("Manche 2 -> Manche 3 : partie %s avancée", code)

    return {
        "message": "Successfully advanced to round 3 (memory grid)",
        "current_round": game.current_round.value
    }

# Round 3 Enhanced Memory Grid Endpoints
@router.post("/games/{code}/memory-grid/create-with-themes", response_model=schemas.MemoryGrid)
def create_memory_grid_with_themes(code: str, rows: int = 5, cols: int = 7, db: Session = Depends(get_db), _host: models.GameSession = Depends(require_host)):
    """
    Create memory grid for Round 3 with theme-based cell assignment.
    Uses team.selected_theme_ids to assign 5 cells per team.
    """
    game = db.query(models.GameSession).filter(models.GameSession.code == code).first()
    if not game:
        raise HTTPException(status_code=404, detail="Session de jeu non trouvée")

    # Verify game is in round 3
    if game.current_round != models.RoundType.MANCHE_3:
        raise HTTPException(status_code=400, detail="La grille mémoire avec thèmes est seulement disponible en manche 3")

    # H.011 : idempotence, comme create_memory_grid — le client (écran de
    # setup) peut détecter "tous les finalistes prêts" par deux voies
    # concurrentes (polling + dernière soumission du picker) et appeler cet
    # endpoint deux fois quasi simultanément. Sans ce garde, ça créerait deux
    # grilles pour la même partie.
    existing = db.query(MemoryGrid).filter(
        MemoryGrid.game_session_id == game.id,
        MemoryGrid.is_completed == False
    ).first()
    if existing:
        return existing

    manager = MemoryGridManager(db)
    try:
        memory_grid = manager.create_memory_grid_with_themes(game.id, rows=rows, cols=cols)
        return memory_grid
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/games/{code}/memory-grid/finalists")
def get_finalists_from_round2(code: str, db: Session = Depends(get_db)):
    """
    Les 4 finalistes de la Manche 3, classés par score de Manche 2.
    AD-0 : la Manche 3 est individuelle — on classe des JOUEURS.
    """
    game = db.query(models.GameSession).filter(models.GameSession.code == code).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game session not found")

    manager = MemoryGridManager(db)
    try:
        finalists = manager.get_finalists_from_round2(game.id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return {
        "finalists": finalists,
        "game_session_id": game.id
    }

@router.get("/games/{code}/memory-grid/standings")
def get_memory_grid_standings(code: str, db: Session = Depends(get_db)):
    """
    Classement final des finalistes de la Manche 3, adressé par code de partie.

    AD-1 : c'est la Manche 3 SEULE qui désigne le vainqueur du tournoi ; aucun
    score des manches 1 ou 2 n'entre dans ce classement.
    """
    from app.memory_grid_enhanced import MemoryGridEnhancer

    game = db.query(models.GameSession).filter(models.GameSession.code == code).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game session not found")

    memory_grid = _get_active_memory_grid(db, game)

    try:
        return MemoryGridEnhancer(db).calculate_winner(memory_grid.id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/games/{code}/memory-grid/state")
def get_memory_grid_state_by_code(code: str, db: Session = Depends(get_db)):
    """
    BUG-401 (#32) : decouverte de l'etat de la grille memoire par code de
    partie, pour un spectateur (joueur elimine en Manche 1/2) qui ne connait
    jamais le memory_grid_id -- celui-ci n'est obtenu par un finaliste que
    via son propre flux de setup (initGrid). Reste public au meme niveau que
    GET /memory-grid/{memory_grid_id}/state (aucune verification
    d'appartenance) : un spectateur ne voit rien de plus qu'un finaliste au
    meme instant.
    """
    game = db.query(models.GameSession).filter(models.GameSession.code == code).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game session not found")

    memory_grid = _get_active_memory_grid(db, game)

    manager = MemoryGridManager(db)
    grid_state = manager.get_grid_state(memory_grid.id)
    if not grid_state:
        raise HTTPException(status_code=404, detail="Grille mémoire non trouvée")

    return grid_state


def _get_active_memory_grid(db: Session, game: models.GameSession) -> MemoryGrid:
    memory_grid = db.query(MemoryGrid).filter(
        MemoryGrid.game_session_id == game.id
    ).order_by(MemoryGrid.id.desc()).first()
    if not memory_grid:
        raise HTTPException(status_code=404, detail="Aucune grille mémoire pour cette partie")
    return memory_grid


@router.post("/games/{code}/memory-grid/sudden-death/start", response_model=schemas.SuddenDeathStateResponse)
def start_sudden_death(code: str, db: Session = Depends(get_db), _host: models.GameSession = Depends(require_host)):
    """
    Story L.001 (BUG-305) : déclenche la mort subite quand la Manche 3 se
    termine sur une égalité. Idempotent (AD-7) : rejouable sans effet de
    bord si une mort subite non résolue est déjà en cours.
    """
    game = db.query(models.GameSession).filter(models.GameSession.code == code).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game session not found")

    from app.memory_grid_enhanced import MemoryGridEnhancer

    memory_grid = _get_active_memory_grid(db, game)

    try:
        round_obj = MemoryGridEnhancer(db).start_sudden_death(memory_grid.id)
        db.commit()
    except LookupError as e:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

    question = db.query(models.Question).filter(models.Question.id == round_obj.question_id).first()
    return schemas.SuddenDeathStateResponse(
        id=round_obj.id,
        question_text=question.text if question else "",
        tied_player_ids=round_obj.tied_player_ids or [],
        eliminated_player_ids=round_obj.eliminated_player_ids or [],
        is_completed=round_obj.is_completed,
        winner_player_id=round_obj.winner_player_id,
    )


@router.post("/games/{code}/memory-grid/sudden-death/answer", response_model=schemas.SuddenDeathAnswerResponse)
def answer_sudden_death(code: str, request: schemas.SuddenDeathAnswerRequest, db: Session = Depends(get_db)):
    """
    Story L.001 : soumission de réponse en mort subite. Pas de garde host —
    la Manche 3 est un écran partagé sans identité par appareil (cf.
    project-context.md, "Reconnection is server-derived").
    """
    game = db.query(models.GameSession).filter(models.GameSession.code == code).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game session not found")

    from app.memory_grid_enhanced import MemoryGridEnhancer

    try:
        result = MemoryGridEnhancer(db).answer_sudden_death(
            request.sudden_death_round_id, request.player_id, request.player_answer
        )
        db.commit()
        return result
    except LookupError as e:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/games/{code}/memory-grid/sudden-death/state", response_model=Optional[schemas.SuddenDeathStateResponse])
def get_sudden_death_state(code: str, db: Session = Depends(get_db)):
    """Story L.001 : état courant de la mort subite (polling), ou null."""
    game = db.query(models.GameSession).filter(models.GameSession.code == code).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game session not found")

    memory_grid = _get_active_memory_grid(db, game)

    round_obj = db.query(SuddenDeathRound).filter(
        SuddenDeathRound.memory_grid_id == memory_grid.id
    ).order_by(SuddenDeathRound.id.desc()).first()
    if not round_obj:
        return None

    question = db.query(models.Question).filter(models.Question.id == round_obj.question_id).first()
    return schemas.SuddenDeathStateResponse(
        id=round_obj.id,
        question_text=question.text if question else "",
        tied_player_ids=round_obj.tied_player_ids or [],
        eliminated_player_ids=round_obj.eliminated_player_ids or [],
        is_completed=round_obj.is_completed,
        winner_player_id=round_obj.winner_player_id,
    )


@router.get("/memory-grid/{memory_grid_id}/current-player-turn")
def get_current_player_turn(memory_grid_id: int, db: Session = Depends(get_db)):
    """
    Le finaliste dont c'est le tour, en tourniquet sur le classement de Manche 2.
    """
    manager = MemoryGridManager(db)

    memory_grid = db.query(MemoryGrid).filter(MemoryGrid.id == memory_grid_id).first()
    if not memory_grid:
        raise HTTPException(status_code=404, detail="Memory grid not found")

    try:
        finalists = manager.get_finalists_from_round2(memory_grid.game_session_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))

    current_player_id = manager.get_current_player_turn(memory_grid_id, finalists)

    return {
        "memory_grid_id": memory_grid_id,
        "current_turn": memory_grid.current_turn,
        "finalists": finalists,
        "current_player_id": current_player_id
    }

@router.get("/games/{code}/available-colors")
def get_available_colors(code: str, db: Session = Depends(get_db)):
    """
    Get available colors for selection in Round 3.
    Returns list of PlayerColor enum values that are not already taken.
    """
    game = db.query(models.GameSession).filter(models.GameSession.code == code).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game session not found")

    manager = MemoryGridManager(db)
    try:
        available_colors = manager.get_available_colors(game.id)
        return {
            "available_colors": available_colors,
            "game_session_id": game.id
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting available colors: {str(e)}")

@router.post("/memory-grid/select-color")
def select_player_color(request: schemas.ColorSelectionRequest, db: Session = Depends(get_db)):
    """
    Attribuer une couleur à un finaliste de la Manche 3.

    AD-0 : les couleurs appartiennent aux joueurs, pas aux équipes.
    AD-12 : l'entrée passe par le corps de requête, jamais en paramètre d'URL.
    AD-5 : l'endpoint possède la transaction.
    """
    manager = MemoryGridManager(db)
    try:
        result = manager.select_player_color(
            request.game_session_id, request.player_id, request.color
        )
        db.commit()
        return result
    except LookupError as e:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))