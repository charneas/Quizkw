import json
import logging
import random

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app import models, schemas
from app.round2_manager import Round2Manager
from app.game_helpers import require_host, require_host_by_game_code

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/games/{code}/qualify-round2")
def qualify_players_from_round1(code: str, db: Session = Depends(get_db), _host: models.GameSession = Depends(require_host)):
    """
    Qualifier les 8 joueurs de la Manche 2 depuis les meilleures équipes.

    AD-0 : Manche 1 collective -> Manche 2 individuelle (8 joueurs).
    AD-7 : c'est cette transition qui pose enfin MANCHE_2.
    AD-5 : l'endpoint possède la transaction.
    """
    game = db.query(models.GameSession).filter(models.GameSession.code == code).first()
    if not game:
        raise HTTPException(status_code=404, detail="Session de jeu non trouvée")

    manager = Round2Manager(db)
    try:
        result = manager.qualify_players_from_round1(game.id)
        db.commit()
        return result
    except LookupError as e:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


# Round 2 Endpoints (16→8→4 Tournament)
@router.get("/round2/{game_code}/players")
def get_round2_qualified_players(game_code: str, db: Session = Depends(get_db)):
    """
    Liste des joueurs qualifiés pour la Manche 2 (ceux ayant une ligne
    PlayerRound2Stats pour cette partie), pour permettre à un appareil de se
    reconnecter sous SA véritable identité au lieu de créer un joueur libre
    non lié à la qualification de la Manche 1 (bug utilisateur).
    """
    game = db.query(models.GameSession).filter(models.GameSession.code == game_code).first()
    if not game:
        raise HTTPException(status_code=404, detail="Session de jeu non trouvée")

    stats = db.query(models.PlayerRound2Stats).filter(
        models.PlayerRound2Stats.game_session_id == game.id
    ).all()
    stats_by_player_id = {s.player_id: s for s in stats}
    player_ids = list(stats_by_player_id.keys())
    players = db.query(models.Player).filter(models.Player.id.in_(player_ids)).all()
    teams_by_id = {t.id: t for t in db.query(models.Team).filter(
        models.Team.id.in_([p.team_id for p in players if p.team_id])
    ).all()}
    themes_by_id = {t.id: t for t in db.query(models.Theme).filter(
        models.Theme.id.in_([s.theme_id for s in stats if s.theme_id])
    ).all()}

    def stats_payload(s: models.PlayerRound2Stats):
        theme = themes_by_id.get(s.theme_id) if s.theme_id else None
        return {
            "theme_id": s.theme_id,
            "theme": {
                "id": theme.id,
                "name": theme.name,
                "category": theme.category,
                "difficulty_level": theme.difficulty_level,
                "description": theme.description,
                "created_at": theme.created_at,
            } if theme else None,
            "score": s.score,
            "questions_answered": s.questions_answered,
            "correct_answers": s.correct_answers,
            "current_question_index": s.current_question_index,
            "qualification_status": s.qualification_status,
            "completed_at": s.completed_at,
        }

    return [
        {
            "id": p.id,
            "name": p.name,
            "team_id": p.team_id,
            "team_name": teams_by_id[p.team_id].name if p.team_id in teams_by_id else None,
            # BUG-207 : la stats du joueur est renvoyée ici pour permettre au
            # front de restaurer selectedTheme/currentQuestion au reconnect
            # au lieu de retomber sur ThemeSelector (qui échoue avec "already
            # selected a theme" si un thème a déjà été choisi).
            "round2_stats": stats_payload(stats_by_player_id[p.id]) if p.id in stats_by_player_id else None,
        }
        for p in players
    ]

@router.get("/round2/{game_code}/themes")
def get_round2_themes(game_code: str, db: Session = Depends(get_db)):
    """
    Get 3 random themes for Round 2 selection
    """
    game = db.query(models.GameSession).filter(models.GameSession.code == game_code).first()
    if not game:
        raise HTTPException(status_code=404, detail="Session de jeu non trouvée")

    manager = Round2Manager(db)
    themes = manager.get_available_themes(game.id, count=3)

    return {
        "themes": themes,
        "game_session_id": game.id
    }

@router.post("/round2/{game_code}/select-theme", response_model=schemas.ThemeSelectionResponse)
def select_theme(game_code: str, theme_request: schemas.ThemeSelectionRequest, db: Session = Depends(get_db)):
    """
    Select a theme for a player in Round 2
    """
    game = db.query(models.GameSession).filter(models.GameSession.code == game_code).first()
    if not game:
        raise HTTPException(status_code=404, detail="Session de jeu non trouvée")

    # CRITICAL FIX: Clear session cache before creating manager
    # This prevents SQLAlchemy object identity issues
    db.expire_all()

    manager = Round2Manager(db)

    # Verify that the player exists
    player = db.query(models.Player).filter(models.Player.id == theme_request.player_id).first()
    if not player:
        raise HTTPException(status_code=404, detail="Joueur non trouvé")

    try:
        print(f"DEBUG: Starting select_theme for player_id={theme_request.player_id}, theme_id={theme_request.theme_id}")

        stats = manager.select_theme(theme_request.player_id, game.id, theme_request.theme_id)
        print(f"DEBUG: manager.select_theme returned: player_id={stats.player_id}, id={stats.id}")

        theme = db.query(models.Theme).filter(models.Theme.id == theme_request.theme_id).first()
        print(f"DEBUG: Theme found: {theme.name if theme else 'None'}")

        # BEST PRACTICE FIX: Use manual data extraction to avoid SQLAlchemy object identity issues
        # Query fresh stats and extract data manually
        fresh_stats = db.query(models.PlayerRound2Stats).filter(
            models.PlayerRound2Stats.player_id == theme_request.player_id,
            models.PlayerRound2Stats.game_session_id == game.id
        ).first()

        # ULTIMATE FIX: Check what the query actually returned BEFORE any other checks
        print(f"ULTIMATE DEBUG: Query for player_id={theme_request.player_id}, game_id={game.id}")
        print(f"ULTIMATE DEBUG: Query returned: {fresh_stats}")
        if fresh_stats:
            print(f"ULTIMATE DEBUG: fresh_stats.player_id = {fresh_stats.player_id}")
            print(f"ULTIMATE DEBUG: fresh_stats.id = {fresh_stats.id}")

        # Check if query returned anything
        if not fresh_stats:
            # This is a CRITICAL BUG - manager.select_theme should have created stats
            # But it created/modified the wrong player (player 7)
            raise HTTPException(
                status_code=500,
                detail=f"BUG CRITIQUE : aucune statistique trouvée pour le joueur {theme_request.player_id} après select_theme."
            )

        # CRITICAL FIX: Verify the query returned the correct player
        # This catches SQLAlchemy query bugs
        if fresh_stats.player_id != theme_request.player_id:
            raise HTTPException(
                status_code=500,
                detail=f"BUG : la requête a retourné le mauvais joueur (attendu {theme_request.player_id}, obtenu {fresh_stats.player_id})"
            )

        # ULTIMATE FIX: Also verify the object in the database matches
        # Query ALL stats to see what's really in the database
        all_stats = db.query(models.PlayerRound2Stats).all()
        print(f"ULTIMATE DEBUG: All PlayerRound2Stats in database: {len(all_stats)}")
        for s in all_stats:
            print(f"ULTIMATE DEBUG: Player {s.player_id}: id={s.id}, theme_id={s.theme_id}")

        # Final verification: The object must have the correct player_id
        # If this fails, there's a fundamental SQLAlchemy/database bug
        if fresh_stats.player_id != theme_request.player_id:
            # This should never happen if the assertion above worked
            # But we check again for absolute certainty
            raise HTTPException(
                status_code=500,
                detail=f"BUG CRITIQUE : l'objet en base a le mauvais player_id "
                       f"(attendu {theme_request.player_id}, obtenu {fresh_stats.player_id})."
            )

        # Create a dictionary with the exact data we want to return
        # This avoids SQLAlchemy/Pydantic serialization issues
        player_stats_data = {
            "id": fresh_stats.id,
            "player_id": fresh_stats.player_id,
            "game_session_id": fresh_stats.game_session_id,
            "theme_id": fresh_stats.theme_id,
            "score": fresh_stats.score,
            "questions_answered": fresh_stats.questions_answered,
            "correct_answers": fresh_stats.correct_answers,
            "current_question_index": fresh_stats.current_question_index,
            "qualification_status": fresh_stats.qualification_status.value,
            "theme_selected_at": fresh_stats.theme_selected_at,
            "completed_at": fresh_stats.completed_at
        }

        print(f"DEBUG: Returning success response with player_id={player_stats_data['player_id']}")

        # Create the response with manually constructed data
        return schemas.ThemeSelectionResponse(
            theme=theme,
            player_stats=player_stats_data,  # Pass dict instead of SQLAlchemy object
            message=f"Thème « {theme.name} » sélectionné avec succès"
        )
    except ValueError as e:
        print(f"DEBUG: ValueError caught in select_theme endpoint: {e}")
        print(f"DEBUG: But we're returning 400 with error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException as e:
        print(f"DEBUG: HTTPException caught: {e.detail}")
        raise e
    except Exception as e:
        print(f"DEBUG: Unexpected exception: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur inattendue : {str(e)}")

@router.get("/round2/{game_code}/question", response_model=schemas.Round2QuestionResponse)
def get_round2_question(game_code: str, player_id: int, db: Session = Depends(get_db)):
    """
    Get the next question for a player in Round 2
    """
    game = db.query(models.GameSession).filter(models.GameSession.code == game_code).first()
    if not game:
        raise HTTPException(status_code=404, detail="Session de jeu non trouvée")

    manager = Round2Manager(db)

    try:
        question = manager.get_next_question(player_id, game.id)
        if not question:
            raise HTTPException(status_code=404, detail="Aucune question disponible — le joueur a peut-être déjà terminé")

        # Shuffle options
        wrong_answers = json.loads(question.wrong_answers) if question.wrong_answers else []
        options = wrong_answers + [question.correct_answer]
        random.shuffle(options)

        return schemas.Round2QuestionResponse(
            question=question,
            question_number=question.question_number,
            difficulty=question.question_number,
            options=options,
            time_limit=30
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/round2/{game_code}/answer", response_model=schemas.Round2AnswerResponse)
def submit_round2_answer(game_code: str, answer_request: schemas.Round2AnswerRequest, db: Session = Depends(get_db)):
    """
    Submit an answer to a Round 2 question
    """
    game = db.query(models.GameSession).filter(models.GameSession.code == game_code).first()
    if not game:
        raise HTTPException(status_code=404, detail="Session de jeu non trouvée")

    manager = Round2Manager(db)

    try:
        result = manager.submit_answer(answer_request.player_id, game.id, answer_request.question_id, answer_request.player_answer)

        return schemas.Round2AnswerResponse(
            is_correct=result["is_correct"],
            points_awarded=result["points_awarded"],
            player_score=result["player_score"],
            correct_answer=result["correct_answer"],
            next_question_available=result["next_question_available"],
            qualification_status=result["qualification_status"],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/round2/{game_code}/leaderboard", response_model=schemas.IntermediateLeaderboardResponse)
def get_round2_leaderboard(game_code: str, db: Session = Depends(get_db)):
    """
    Get intermediate leaderboard (top 8 qualified)
    """
    game = db.query(models.GameSession).filter(models.GameSession.code == game_code).first()
    if not game:
        raise HTTPException(status_code=404, detail="Session de jeu non trouvée")

    manager = Round2Manager(db)
    leaderboard = manager.calculate_intermediate_leaderboard(game.id)

    return leaderboard

@router.post("/round2/{game_code}/advance", response_model=schemas.Round2AdvanceResponse)
def advance_round2_phase(game_code: str, db: Session = Depends(get_db), _host: models.GameSession = Depends(require_host_by_game_code)):
    """
    Advance to the next phase (16→8 or 8→4)
    """
    game = db.query(models.GameSession).filter(models.GameSession.code == game_code).first()
    if not game:
        raise HTTPException(status_code=404, detail="Session de jeu non trouvée")

    manager = Round2Manager(db)

    # H-007 : le bouton "Manche 2 →" n'a jamais appelé qualify-round2 ; sans
    # PlayerRound2Stats, la qualification n'a jamais eu lieu. On la déclenche
    # ici pour que /round2/{code}/advance fonctionne seul depuis la Manche 1.
    if game.current_round == models.RoundType.MANCHE_1:
        try:
            result = manager.qualify_players_from_round1(game.id)
            db.commit()
        except (LookupError, ValueError) as e:
            db.rollback()
            logger.warning("qualify_players_from_round1 rejeté pour %s : %s", game_code, e)
            raise HTTPException(status_code=400, detail=str(e))
        except IntegrityError:
            db.rollback()
            logger.warning("qualify_players_from_round1 en conflit pour %s (rejeu concurrent)", game_code)
            raise HTTPException(status_code=409, detail="Qualification déjà en cours ou en conflit, réessayez")
        logger.info(
            "Manche 1 -> Manche 2 : %s joueurs qualifiés pour %s", result["qualified_count"], game_code
        )
        return schemas.Round2AdvanceResponse(
            new_phase="16_players",
            qualified_count=result["qualified_count"],
            eliminated_count=0,
            message=f"{result['qualified_count']} joueurs qualifiés pour la Manche 2"
        )

    # Check current phase
    progress = manager.get_tournament_progress(game.id)

    if progress.phase == "16_players":
        # Check if all players have finished
        all_players = db.query(models.PlayerRound2Stats).filter(
            models.PlayerRound2Stats.game_session_id == game.id
        ).all()

        completed_players = [p for p in all_players if p.current_question_index >= 10]
        if len(completed_players) < len(all_players):
            raise HTTPException(
                status_code=400,
                detail=f"Tous les joueurs doivent terminer avant de pouvoir avancer ({len(completed_players)}/{len(all_players)} terminés)"
            )

        # Advance to 8 qualified
        leaderboard = manager.calculate_intermediate_leaderboard(game.id)
        return schemas.Round2AdvanceResponse(
            new_phase="8_qualified",
            qualified_count=len(leaderboard.qualified_players),
            eliminated_count=len(leaderboard.eliminated_players),
            message="Phase 16→8 terminée, les meilleurs qualifiés"
        )

    elif progress.phase == "8_qualified":
        # Ne pas promouvoir tant qu'un joueur qualifié joue encore sa Manche 2
        # (get_tournament_progress passe en "8_qualified" dès que 8 joueurs
        # ont terminé, même si un 9e est toujours PLAYING).
        still_playing = db.query(models.PlayerRound2Stats).filter(
            models.PlayerRound2Stats.game_session_id == game.id,
            models.PlayerRound2Stats.qualification_status == models.QualificationStatus.PLAYING,
        ).count()
        if still_playing:
            logger.info(
                "Manche 2 -> Manche 3 différée pour %s : %s joueur(s) encore en jeu",
                game_code, still_playing,
            )
            raise HTTPException(
                status_code=400,
                detail=f"{still_playing} joueur(s) qualifié(s) n'ont pas encore terminé la Manche 2"
            )

        # Advance to 4 finalists
        try:
            result = manager.advance_to_finalists(game.id)
        except ValueError as e:
            logger.warning("advance_to_finalists rejeté pour %s : %s", game_code, e)
            raise HTTPException(status_code=400, detail=str(e))
        logger.info("Manche 2 -> Manche 3 : 4 finalistes désignés pour %s", game_code)
        return result

    else:
        raise HTTPException(status_code=400, detail="Le tournoi est déjà dans sa phase finale")

@router.get("/round2/{game_code}/progress", response_model=schemas.TournamentProgress)
def get_round2_progress(game_code: str, db: Session = Depends(get_db)):
    """
    Get tournament progression 16→8→4
    """
    game = db.query(models.GameSession).filter(models.GameSession.code == game_code).first()
    if not game:
        raise HTTPException(status_code=404, detail="Session de jeu non trouvée")

    manager = Round2Manager(db)
    progress = manager.get_tournament_progress(game.id)

    return progress