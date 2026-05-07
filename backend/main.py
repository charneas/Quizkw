from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import random
import string
from sqlalchemy.orm import Session

from app.database import get_db, engine
from app import models, schemas
from app.models import Base
from app.memory_grid import MemoryGridManager, MemoryGrid, GridCell, MemoryGridRound, GridCellStatus
from app.round2_manager import Round2Manager
from main_extended import router

# Create database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Quizkw API",
    description="API pour le jeu de quiz Quizkw avec règles complexes",
    version="1.0.0"
)

# Configure CORS to allow requests from the frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Replace with frontend URL in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include extended endpoints for Memory Grid Round 3
app.include_router(router)

# Generate a random session code
def generate_session_code(length=6):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

@app.get("/")
def read_root():
    return {"message": "Bienvenue sur l'API Quizkw !", "version": "1.0.0"}

@app.get("/health")
def health_check():
    return {"status": "healthy"}

@app.post("/games/", response_model=schemas.GameSessionResponse)
def create_game(game_create: schemas.GameSessionCreate, db: Session = Depends(get_db)):
    """
    Créer une nouvelle session de jeu
    """
    # Générer un code unique
    code = generate_session_code()
    while db.query(models.GameSession).filter(models.GameSession.code == code).first():
        code = generate_session_code()
    
    # Créer la session
    game = models.GameSession(
        code=code,
        total_players=game_create.total_players,
        players_per_team=game_create.players_per_team,
        current_round=models.RoundType.MANCHE_1,
        is_active=True
    )
    
    db.add(game)
    db.commit()
    db.refresh(game)
    
    return {
        "game": game,
        "message": f"Session de jeu créée avec le code: {code}"
    }

@app.get("/games/{code}", response_model=schemas.GameSession)
def get_game(code: str, db: Session = Depends(get_db)):
    """
    Récupérer une session de jeu par son code
    """
    game = db.query(models.GameSession).filter(models.GameSession.code == code).first()
    if not game:
        raise HTTPException(status_code=404, detail="Session de jeu non trouvée")
    return game

@app.post("/games/{code}/teams/", response_model=schemas.Team)
def create_team(code: str, team_create: schemas.TeamCreate, db: Session = Depends(get_db)):
    """
    Créer une équipe dans une session de jeu
    """
    game = db.query(models.GameSession).filter(models.GameSession.code == code).first()
    if not game:
        raise HTTPException(status_code=404, detail="Session de jeu non trouvée")
    
    # Vérifier le nombre maximum d'équipes
    max_teams = game.total_players // game.players_per_team
    current_teams = db.query(models.Team).filter(models.Team.game_session_id == game.id).count()
    
    if current_teams >= max_teams:
        raise HTTPException(status_code=400, detail="Nombre maximum d'équipes atteint")
    
    team = models.Team(
        name=team_create.name,
        game_session_id=game.id,
        score=0
    )
    
    db.add(team)
    db.commit()
    db.refresh(team)
    
    # Donner 3 jetons à l'équipe
    token_types = [models.TokenType.SWAP, models.TokenType.PENALTY, models.TokenType.BONUS]
    for token_type in token_types:
        token = models.Token(
            team_id=team.id,
            token_type=token_type,
            is_used=False
        )
        db.add(token)
    
    db.commit()
    
    return team

@app.post("/games/{code}/start")
def start_game(code: str, db: Session = Depends(get_db)):
    """
    Démarrer une session de jeu
    """
    game = db.query(models.GameSession).filter(models.GameSession.code == code).first()
    if not game:
        raise HTTPException(status_code=404, detail="Session de jeu non trouvée")
    
    # Vérifier qu'il y a au moins 2 équipes
    teams = db.query(models.Team).filter(models.Team.game_session_id == game.id).all()
    if len(teams) < 2:
        raise HTTPException(status_code=400, detail="Au moins 2 équipes sont nécessaires pour démarrer")
    
    # Vérifier que chaque équipe a le bon nombre de joueurs
    for team in teams:
        players = db.query(models.Player).filter(models.Player.team_id == team.id).count()
        if players != game.players_per_team:
            raise HTTPException(
                status_code=400, 
                detail=f"L'équipe {team.name} doit avoir {game.players_per_team} joueurs"
            )
    
    game.is_active = True
    db.commit()
    
    return {"message": "Jeu démarré avec succès", "teams": len(teams)}

@app.post("/games/{code}/players/", response_model=schemas.Player)
def create_player(code: str, player_create: schemas.PlayerCreate, db: Session = Depends(get_db)):
    """
    Create a player in a game session (for Round 2 individual play)
    """
    game = db.query(models.GameSession).filter(models.GameSession.code == code).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game session not found")
    
    # For Round 2, players can be created without team (will be assigned later or stay individual)
    player = models.Player(
        name=player_create.name,
        team_id=None  # Allow null for Round 2 individual play
    )
    
    db.add(player)
    db.commit()
    db.refresh(player)
    
    return player

@app.get("/questions/random", response_model=schemas.QuestionResponse)
def get_random_question(category: str = None, difficulty: schemas.DifficultyEnum = None, db: Session = Depends(get_db)):
    """
    Obtenir une question aléatoire
    """
    query = db.query(models.Question)
    
    if category:
        query = query.filter(models.Question.category == category)
    if difficulty:
        query = query.filter(models.Question.difficulty == difficulty)
    
    question = query.order_by(models.models.func.random()).first()
    
    if not question:
        raise HTTPException(status_code=404, detail="Aucune question trouvée")
    
    # Mélanger les réponses
    import json
    wrong_answers = json.loads(question.wrong_answers) if question.wrong_answers else []
    options = wrong_answers + [question.correct_answer]
    random.shuffle(options)
    
    return {
        "question": question,
        "options": options
    }

@app.post("/answers/", response_model=schemas.AnswerResponse)
def submit_answer(answer_create: schemas.AnswerCreate, db: Session = Depends(get_db)):
    """
    Soumettre une réponse à une question
    """
    question = db.query(models.Question).filter(models.Question.id == answer_create.question_id).first()
    if not question:
        raise HTTPException(status_code=404, detail="Question non trouvée")
    
    team = db.query(models.Team).filter(models.Team.id == answer_create.team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Équipe non trouvée")
    
    # Vérifier si la réponse est correcte
    is_correct = answer_create.player_answer.strip().lower() == question.correct_answer.strip().lower()
    points_earned = question.points if is_correct else 0
    
    # Ajouter les points à l'équipe
    team.score += points_earned
    
    # Enregistrer la réponse
    answer = models.Answer(
        question_id=answer_create.question_id,
        team_id=answer_create.team_id,
        player_answer=answer_create.player_answer,
        is_correct=is_correct,
        points_earned=points_earned
    )
    
    db.add(answer)
    db.commit()
    db.refresh(team)
    
    return {
        "is_correct": is_correct,
        "correct_answer": question.correct_answer,
        "points_earned": points_earned,
        "team_score": team.score
    }

@app.post("/tokens/use")
def use_token(token_use: schemas.TokenUseRequest, db: Session = Depends(get_db)):
    """
    Utiliser un jeton
    """
    # Chercher un jeton non utilisé du type demandé pour l'équipe
    token = db.query(models.Token).filter(
        models.Token.team_id == token_use.team_id,
        models.Token.token_type == token_use.token_type,
        models.Token.is_used == False
    ).first()
    
    if not token:
        raise HTTPException(status_code=404, detail="Jeton non disponible")
    
    token.is_used = True
    db.commit()
    
    # Appliquer l'effet du jeton
    effect_message = ""
    if token_use.token_type == schemas.TokenTypeEnum.swap:
        effect_message = "SWAP ! Changement de catégorie activé"
    elif token_use.token_type == schemas.TokenTypeEnum.penalty:
        effect_message = "Don de pénalité activé"
    elif token_use.token_type == schemas.TokenTypeEnum.bonus:
        effect_message = "Question bonus activée - double des points sur la prochaine question"
    
    return {
        "message": f"Jeton {token_use.token_type} utilisé avec succès",
        "effect": effect_message,
        "token_id": token.id
    }

@app.post("/wheel/spin", response_model=schemas.WheelSpinResponse)
def spin_wheel(wheel_spin: schemas.WheelSpinRequest, db: Session = Depends(get_db)):
    """
    Tourner la roue de bonus/malus (tous les 5 tours selon les règles)
    """
    # Simuler un spin de roue avec les probabilités des règles
    # 1-5: malus de 3 points
    # 6-10: +1 point ou récupération jeton
    # 11-18: ping pong (+2 points au vainqueur)
    # 19-20: +3 points
    
    spin_result = random.randint(1, 20)
    
    if spin_result <= 5:
        return {
            "effect_type": "malus",
            "value": -3,
            "message": f"Résultat {spin_result}: Malus de 3 points"
        }
    elif spin_result <= 10:
        # Demander au frontend ce qu'il préfère: +1 point ou récupération jeton
        return {
            "effect_type": "choice",
            "value": 1,
            "message": f"Résultat {spin_result}: Choisissez +1 point OU récupération d'un jeton"
        }
    elif spin_result <= 18:
        return {
            "effect_type": "ping_pong",
            "value": 2,
            "message": f"Résultat {spin_result}: Mode Ping Pong! Choisissez un adversaire, +2 points au vainqueur"
        }
    else:  # 19-20
        return {
            "effect_type": "bonus",
            "value": 3,
            "message": f"Résultat {spin_result}: Bonus de 3 points!"
        }

# Phase 3 - Memory Grid Endpoints
@app.post("/games/{code}/memory-grid/create", response_model=schemas.MemoryGrid)
def create_memory_grid(code: str, db: Session = Depends(get_db)):
    """
    Créer une grille mémoire pour la manche 3 (7x5 grid)
    """
    game = db.query(models.GameSession).filter(models.GameSession.code == code).first()
    if not game:
        raise HTTPException(status_code=404, detail="Session de jeu non trouvée")
    
    # Vérifier que le jeu est à la manche 3
    if game.current_round != models.RoundType.MANCHE_3:
        raise HTTPException(status_code=400, detail="La grille mémoire est seulement disponible en manche 3")
    
    manager = MemoryGridManager(db)
    memory_grid = manager.create_memory_grid(game.id, rows=7, cols=5)
    
    return memory_grid

@app.post("/games/{code}/memory-grid/start", response_model=schemas.StartMemoryGridRoundResponse)
def start_memory_grid_round(code: str, db: Session = Depends(get_db)):
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
    
    manager = MemoryGridManager(db)
    round_obj = manager.start_memory_grid_round(game.id, memory_grid.id)
    
    return {
        "round_id": round_obj.id,
        "message": "Tour de grille mémoire démarré"
    }

@app.get("/memory-grid/{memory_grid_id}/state", response_model=schemas.MemoryGridStateResponse)
def get_memory_grid_state(memory_grid_id: int, db: Session = Depends(get_db)):
    """
    Obtenir l'état actuel de la grille mémoire
    """
    manager = MemoryGridManager(db)
    grid_state = manager.get_grid_state(memory_grid_id)
    
    if not grid_state:
        raise HTTPException(status_code=404, detail="Grille mémoire non trouvée")
    
    return grid_state

@app.post("/memory-grid/reveal-cell")
def reveal_cell(reveal_request: schemas.SelectCellRequest, db: Session = Depends(get_db)):
    """
    Révéler une cellule dans la grille mémoire
    """
    manager = MemoryGridManager(db)
    result = manager.reveal_cell(reveal_request.round_id, reveal_request.team_id, reveal_request.cell_id)
    
    if not result:
        raise HTTPException(status_code=404, detail="Erreur lors de la révélation de la cellule")
    
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    
    return result

@app.post("/memory-grid/answer-cell")
def answer_cell(answer_request: schemas.AnswerCellRequest, db: Session = Depends(get_db)):
    """
    Répondre à une cellule révélée dans la grille mémoire
    """
    manager = MemoryGridManager(db)
    result = manager.answer_cell(answer_request.round_id, answer_request.team_id, answer_request.cell_id, answer_request.is_correct)
    
    if not result:
        raise HTTPException(status_code=404, detail="Erreur lors de la réponse à la cellule")
    
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    
    return result

@app.post("/games/{code}/advance-to-phase3")
def advance_to_phase3(code: str, db: Session = Depends(get_db)):
    """
    Pass to phase 3 (final round with memory grid)
    """
    game = db.query(models.GameSession).filter(models.GameSession.code == code).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game session not found")
    
    # Check if game is active and can proceed to phase 3
    if not game.is_active:
        raise HTTPException(status_code=400, detail="Game is not active")
    
    # Advance to round 3
    game.current_round = models.RoundType.MANCHE_3
    db.commit()
    
    return {
        "message": "Successfully advanced to round 3 (memory grid)",
        "current_round": game.current_round.value
    }

# Round 2 Endpoints (16→8→4 Tournament)
@app.get("/round2/{game_code}/themes")
def get_round2_themes(game_code: str, db: Session = Depends(get_db)):
    """
    Get 3 random themes for Round 2 selection
    """
    game = db.query(models.GameSession).filter(models.GameSession.code == game_code).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game session not found")
    
    manager = Round2Manager(db)
    themes = manager.get_available_themes(count=3)
    
    return {
        "themes": themes,
        "game_session_id": game.id
    }

@app.post("/round2/{game_code}/select-theme", response_model=schemas.ThemeSelectionResponse)
def select_theme(game_code: str, theme_request: schemas.ThemeSelectionRequest, db: Session = Depends(get_db)):
    """
    Select a theme for a player in Round 2
    """
    game = db.query(models.GameSession).filter(models.GameSession.code == game_code).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game session not found")
    
    # CRITICAL FIX: Clear session cache before creating manager
    # This prevents SQLAlchemy object identity issues
    db.expire_all()
    
    manager = Round2Manager(db)
    
    # Verify that the player exists
    player = db.query(models.Player).filter(models.Player.id == theme_request.player_id).first()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    
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
                detail=f"CRITICAL BUG: No stats found for player {theme_request.player_id} after select_theme! "
                       f"Manager created/modified wrong player (player 7). "
                       f"This is a fundamental SQLAlchemy object identity bug."
            )
        
        # CRITICAL FIX: Verify the query returned the correct player
        # This catches SQLAlchemy query bugs
        if fresh_stats.player_id != theme_request.player_id:
            raise HTTPException(
                status_code=500, 
                detail=f"BUG: Query returned wrong player! Expected {theme_request.player_id}, got {fresh_stats.player_id}"
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
                detail=f"CRITICAL BUG: Database object has wrong player_id! "
                       f"Expected {theme_request.player_id}, got {fresh_stats.player_id}. "
                       f"This indicates a fundamental SQLAlchemy or database corruption issue."
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
            message=f"Theme '{theme.name}' successfully selected"
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
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")

@app.get("/round2/{game_code}/question", response_model=schemas.Round2QuestionResponse)
def get_round2_question(game_code: str, player_id: int, db: Session = Depends(get_db)):
    """
    Get the next question for a player in Round 2
    """
    game = db.query(models.GameSession).filter(models.GameSession.code == game_code).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game session not found")
    
    manager = Round2Manager(db)
    
    try:
        question = manager.get_next_question(player_id, game.id)
        if not question:
            raise HTTPException(status_code=404, detail="No question available - player may have finished")
        
        # Shuffle options
        import json
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

@app.post("/round2/{game_code}/answer", response_model=schemas.Round2AnswerResponse)
def submit_round2_answer(game_code: str, answer_request: schemas.Round2AnswerRequest, db: Session = Depends(get_db)):
    """
    Submit an answer to a Round 2 question
    """
    game = db.query(models.GameSession).filter(models.GameSession.code == game_code).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game session not found")
    
    manager = Round2Manager(db)
    
    try:
        result = manager.submit_answer(answer_request.player_id, game.id, answer_request.question_id, answer_request.player_answer)
        
        return schemas.Round2AnswerResponse(
            is_correct=result["is_correct"],
            points_awarded=result["points_awarded"],
            player_score=result["player_score"],
            correct_answer=result["correct_answer"],
            next_question_available=result["next_question_available"]
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/round2/{game_code}/leaderboard", response_model=schemas.IntermediateLeaderboardResponse)
def get_round2_leaderboard(game_code: str, db: Session = Depends(get_db)):
    """
    Get intermediate leaderboard (top 8 qualified)
    """
    game = db.query(models.GameSession).filter(models.GameSession.code == game_code).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game session not found")
    
    manager = Round2Manager(db)
    leaderboard = manager.calculate_intermediate_leaderboard(game.id)
    
    return leaderboard

@app.post("/round2/{game_code}/advance", response_model=schemas.Round2AdvanceResponse)
def advance_round2_phase(game_code: str, db: Session = Depends(get_db)):
    """
    Advance to the next phase (16→8 or 8→4)
    """
    game = db.query(models.GameSession).filter(models.GameSession.code == game_code).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game session not found")
    
    manager = Round2Manager(db)
    
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
                detail=f"All players must finish before advancing ({len(completed_players)}/{len(all_players)} completed)"
            )
        
        # Advance to 8 qualified
        leaderboard = manager.calculate_intermediate_leaderboard(game.id)
        return schemas.Round2AdvanceResponse(
            new_phase="8_qualified",
            qualified_count=len(leaderboard.qualified_players),
            eliminated_count=len(leaderboard.eliminated_players),
            message="Phase 16→8 completed, top 8 qualified"
        )
    
    elif progress.phase == "8_qualified":
        # Advance to 4 finalists
        result = manager.advance_to_finalists(game.id)
        return result
    
    else:
        raise HTTPException(status_code=400, detail="Tournament is already in final phase")

@app.get("/round2/{game_code}/progress", response_model=schemas.TournamentProgress)
def get_round2_progress(game_code: str, db: Session = Depends(get_db)):
    """
    Get tournament progression 16→8→4
    """
    game = db.query(models.GameSession).filter(models.GameSession.code == game_code).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game session not found")
    
    manager = Round2Manager(db)
    progress = manager.get_tournament_progress(game.id)
    
    return progress

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
