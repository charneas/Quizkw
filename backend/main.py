from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import random
import string
from sqlalchemy.orm import Session

from app.database import get_db, engine
from app import models, schemas
from app.models import Base

# Créer les tables de la base de données
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Quizkw API",
    description="API pour le jeu de quiz Quizkw avec règles complexes",
    version="1.0.0"
)

# Configurer CORS pour permettre les requêtes depuis le frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # À remplacer par l'URL du frontend en production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Générer un code de session aléatoire
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)