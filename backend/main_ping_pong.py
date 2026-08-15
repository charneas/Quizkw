from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app import manche1_orchestration
from app.game_helpers import require_host, require_team_token, require_team_token_or_host

router = APIRouter()


# Ping-Pong Duel Endpoints
@router.get("/ping-pong/random-theme", response_model=schemas.PingPongTheme)
def get_random_ping_pong_theme(db: Session = Depends(get_db)):
    """
    Get a random ping-pong theme for a duel
    """
    from app.ping_pong_manager import PingPongManager

    manager = PingPongManager(db)
    theme = manager.get_random_theme()

    if not theme:
        raise HTTPException(status_code=404, detail="No ping-pong themes available")

    return theme

@router.post("/ping-pong/duel/start", response_model=schemas.PingPongDuelResponse)
def start_ping_pong_duel(
    request: schemas.StartPingPongDuelRequest,
    db: Session = Depends(get_db),
    x_team_token: Optional[str] = Header(default=None),
    x_host_token: Optional[str] = Header(default=None),
):
    """
    Démarrer un duel ping-pong entre 2 équipes.
    team1_id = équipe qui a tourné la roue (elle commence le duel).
    """
    from app.ping_pong_manager import PingPongManager

    require_team_token_or_host(db, request.team1_id, x_team_token, x_host_token)

    manager = PingPongManager(db)

    try:
        duel = manager.start_duel(
            game_session_id=request.game_session_id,
            theme_id=request.theme_id,
            team1_id=request.team1_id,
            team2_id=request.team2_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Construire la réponse
    theme = db.query(models.PingPongTheme).filter(models.PingPongTheme.id == duel.theme_id).first()
    team1 = db.query(models.Team).filter(models.Team.id == duel.team1_id).first()
    team2 = db.query(models.Team).filter(models.Team.id == duel.team2_id).first()

    return schemas.PingPongDuelResponse(
        duel_id=duel.id,
        theme=schemas.PingPongTheme(
            id=theme.id,
            title=theme.title,
            description=theme.description,
            correct_answers=theme.correct_answers,
            min_answers_to_win=theme.min_answers_to_win,
            created_at=theme.created_at,
        ),
        team1={"id": team1.id, "name": team1.name},
        team2={"id": team2.id, "name": team2.name},
        current_turn_team_id=duel.current_turn_team_id,
        turn_number=1,
        answers_used=duel.answers_used or [],
        is_completed=duel.is_completed,
        winner_team_id=duel.winner_team_id,
    )

@router.post("/ping-pong/duel/answer", response_model=schemas.SubmitPingPongAnswerResponse)
def submit_ping_pong_duel_answer(
    request: schemas.SubmitPingPongAnswerRequest,
    db: Session = Depends(get_db),
    x_team_token: Optional[str] = Header(default=None),
):
    """
    Soumettre une réponse dans un duel ping-pong.
    """
    from app.ping_pong_manager import PingPongManager

    require_team_token(db, request.team_id, x_team_token)

    manager = PingPongManager(db)

    try:
        result = manager.submit_answer(
            duel_id=request.duel_id,
            team_id=request.team_id,
            answer=request.answer,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not result["duel_continues"]:
        duel = db.query(models.PingPongDuel).filter(models.PingPongDuel.id == request.duel_id).first()
        if duel and duel.is_tiebreak:
            # +1 suffit à lever l'ambiguïté de tri sans fausser le classement
            # général (les points de partie s'accordent par 2, 4 ou 6).
            winner = db.query(models.Team).filter(models.Team.id == duel.winner_team_id).first()
            if winner:
                winner.score += 1
                db.commit()
            game = db.query(models.GameSession).filter(models.GameSession.id == duel.game_session_id).first()
            if game:
                manche1_orchestration.resolve_manche1_end(db, game)

    return schemas.SubmitPingPongAnswerResponse(
        is_correct=result["is_correct"],
        answer=result["answer"],
        turn_number=result["turn_number"],
        duel_continues=result["duel_continues"],
        winner_team_id=result["winner_team_id"],
        winner_team_name=result["winner_team_name"],
        next_turn_team_id=result["next_turn_team_id"],
        message=result["message"],
    )

@router.get("/ping-pong/duel/{duel_id}")
def get_ping_pong_duel_state(duel_id: int, db: Session = Depends(get_db)):
    """
    Récupérer l'état actuel d'un duel ping-pong.
    """
    from app.ping_pong_manager import PingPongManager

    manager = PingPongManager(db)

    try:
        state = manager.get_duel_state(duel_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return state

@router.get("/ping-pong/duel/{duel_id}/results")
def get_ping_pong_duel_results(duel_id: int, db: Session = Depends(get_db)):
    """
    Récupérer les résultats finaux d'un duel ping-pong.
    """
    from app.ping_pong_manager import PingPongManager

    manager = PingPongManager(db)

    try:
        results = manager.get_duel_results(duel_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return results

@router.post("/games/{code}/ping-pong/duel/{duel_id}/cancel")
def cancel_ping_pong_duel(code: str, duel_id: int, db: Session = Depends(get_db), _host: models.GameSession = Depends(require_host)):
    """
    Story J.002 (BUG-101g) : le host force la fin d'un duel ping-pong resté
    bloqué (déconnexion, abandon). Libère les deux équipes sans désigner de
    vainqueur ni toucher au score. Le duel de départage de fin de Manche 1
    est hors périmètre (repli existant, #54).
    """
    from app.ping_pong_manager import PingPongManager

    game = db.query(models.GameSession).filter(models.GameSession.code == code).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game session not found")

    duel = db.query(models.PingPongDuel).filter(models.PingPongDuel.id == duel_id).first()
    if not duel or duel.game_session_id != game.id:
        raise HTTPException(status_code=404, detail="Duel introuvable pour cette partie")

    try:
        PingPongManager(db).cancel_duel(duel_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return PingPongManager(db).get_duel_state(duel_id)

@router.post("/games/{code}/ping-pong/duel/{duel_id}/turns/{turn_id}/override")
def override_ping_pong_turn(code: str, duel_id: int, turn_id: int, db: Session = Depends(get_db), _host: models.GameSession = Depends(require_host)):
    """
    BUG-505 (#37) : l'host surclasse manuellement une réponse ping-pong jugée
    incorrecte automatiquement (synonyme, réponse partielle valide...), qui
    avait mis fin au duel. Retire les points crédités au faux gagnant et fait
    reprendre le duel comme si la réponse avait été acceptée d'emblée.
    """
    from app.ping_pong_manager import PingPongManager

    game = db.query(models.GameSession).filter(models.GameSession.code == code).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game session not found")

    duel = db.query(models.PingPongDuel).filter(models.PingPongDuel.id == duel_id).first()
    if not duel or duel.game_session_id != game.id:
        raise HTTPException(status_code=404, detail="Duel introuvable pour cette partie")

    try:
        return PingPongManager(db).override_wrong_answer(duel_id, turn_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))