import logging
import secrets
from typing import Optional
from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
import random
import string
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.database import get_db, engine
from app import models, schemas
from app.models import Base
from app.memory_grid import MemoryGridManager, MemoryGrid, GridCell, MemoryGridRound, GridCellStatus
from app.round2_manager import Round2Manager
from main_extended import router
from main_admin import router as admin_router, auth_router as admin_auth_router
from main_content_gen import router as content_gen_router, player_router as content_flag_router
from main_propositions import router as propositions_router

# E-002 : journalisation minimale au niveau module (voir la spine § Deferred —
# pas d'infrastructure d'observabilité, seulement logging.getLogger standard
# aux points de transition de phase et d'erreur).
# basicConfig est nécessaire : sans configuration explicite, le logger racine
# reste au niveau WARNING par défaut et les logger.info() ajoutés seraient
# silencieusement ignorés (trouvé en revue de code — l'objectif même de
# diagnosticabilité de cette story aurait été vide de sens sans ça).
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

PENALTY_POINTS = 2
MANCHE_1_MAX_QUESTIONS = 20


def award_points_with_bonus(team: models.Team, base_points: int) -> int:
    """Double les points si l'équipe a un jeton BONUS actif, puis le consomme.

    Le bonus s'applique à la question en cours d'être validée, correcte ou
    non — il est consommé dans les deux cas car il visait "cette question".
    """
    points = base_points * 2 if team.bonus_active else base_points
    team.bonus_active = False
    return points

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

from fastapi.responses import JSONResponse
from fastapi import Request


# Include extended endpoints for Memory Grid Round 3
app.include_router(router)
# Include admin login/logout (Epic F-ext-2, story F-ext-2.1) — mounted before
# the guarded admin router, unauthenticated by design (obtaining the cookie)
app.include_router(admin_auth_router)
# Include admin endpoints for content management (Epic F) — guarded since F-ext-2.1 (AD-17)
app.include_router(admin_router)
# Include content generation (F.2) and player flagging endpoints (Epic F)
app.include_router(content_gen_router)
app.include_router(content_flag_router)
# Include public proposition submission endpoint (Epic F-ext, story F-ext-1.1)
app.include_router(propositions_router)

# Generate a random session code
def generate_session_code(length=6):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))


def require_host(code: str, x_host_token: Optional[str] = Header(default=None), db: Session = Depends(get_db)) -> models.GameSession:
    """
    Dépendance FastAPI protégeant les endpoints de contrôle de partie (BUG-103).
    Le host_token est généré à la création de la partie (POST /games/) et
    connu du seul créateur : c'est la seule preuve d'identité host, il n'y a
    pas de notion de compte/session par ailleurs.
    """
    game = db.query(models.GameSession).filter(models.GameSession.code == code).first()
    if not game:
        raise HTTPException(status_code=404, detail="Session de jeu non trouvée")
    if not x_host_token or not secrets.compare_digest(x_host_token, game.host_token):
        raise HTTPException(status_code=403, detail="Action réservée à l'hôte de la partie")
    return game


def require_host_by_game_code(game_code: str, x_host_token: Optional[str] = Header(default=None), db: Session = Depends(get_db)) -> models.GameSession:
    """Variante de require_host pour les routes utilisant `game_code` (Manche 2)."""
    return require_host(game_code, x_host_token, db)

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
        is_active=True,
        started=False,
        host_token=secrets.token_urlsafe(24)
    )

    db.add(game)
    db.commit()
    db.refresh(game)

    return {
        "game": game,
        "message": f"Session de jeu créée avec le code: {code}",
        "host_token": game.host_token
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

    existing_names = db.query(models.Team.name).filter(models.Team.game_session_id == game.id).all()
    if team_create.name.strip().lower() in {n.lower() for (n,) in existing_names}:
        raise HTTPException(status_code=400, detail="Ce nom d'équipe est déjà pris dans cette partie")

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

@app.post("/games/{code}/teams/{team_id}/players/", response_model=schemas.Player)
def join_team(code: str, team_id: int, player_create: schemas.PlayerCreate, db: Session = Depends(get_db)):
    """
    Rejoindre une équipe existante en tant que joueur, avec son pseudo.

    C'est le vrai point d'entrée du pseudo en Manche 1 (auparavant, les
    joueurs n'étaient jamais nommés réellement : `start_game` les générait
    automatiquement en "Player <équipe> <n>" — bug utilisateur). Les joueurs
    ainsi créés sont ensuite ceux qualifiés pour la Manche 2 par
    qualify_players_from_round1, qui lit team.players.
    """
    game = db.query(models.GameSession).filter(models.GameSession.code == code).first()
    if not game:
        raise HTTPException(status_code=404, detail="Session de jeu non trouvée")

    if game.started:
        raise HTTPException(status_code=400, detail="La partie a déjà démarré")

    team = db.query(models.Team).filter(
        models.Team.id == team_id,
        models.Team.game_session_id == game.id,
    ).first()
    if not team:
        raise HTTPException(status_code=404, detail="Équipe non trouvée dans cette partie")

    current_count = db.query(models.Player).filter(models.Player.team_id == team.id).count()
    if current_count >= game.players_per_team:
        raise HTTPException(status_code=400, detail="Cette équipe est déjà complète")

    existing_names = db.query(models.Player.name).filter(models.Player.team_id == team.id).all()
    if player_create.name.strip().lower() in {n.lower() for (n,) in existing_names}:
        raise HTTPException(status_code=400, detail="Ce pseudo est déjà pris dans cette équipe")

    player = models.Player(name=player_create.name, team_id=team.id)
    db.add(player)
    db.commit()
    db.refresh(player)

    return player

@app.post("/games/{code}/start")
def start_game(code: str, db: Session = Depends(get_db), _host: models.GameSession = Depends(require_host)):
    """
    Démarrer une session de jeu (avec auto-fill des joueurs si nécessaire pour le développement)
    """
    game = db.query(models.GameSession).filter(models.GameSession.code == code).first()
    if not game:
        raise HTTPException(status_code=404, detail="Session de jeu non trouvée")
    
    # Vérifier qu'il y a au moins 2 équipes
    teams = db.query(models.Team).filter(models.Team.game_session_id == game.id).all()
    if len(teams) < 2:
        raise HTTPException(status_code=400, detail="Au moins 2 équipes sont nécessaires pour démarrer")
    
    # DEV FIX: Auto-remplir les joueurs si manquants
    for team in teams:
        count = db.query(models.Player).filter(models.Player.team_id == team.id).count()
        if count < game.players_per_team:
            for i in range(game.players_per_team - count):
                p = models.Player(name=f"Player {team.name} {i+1}", team_id=team.id)
                db.add(p)
    db.commit()

    # Vérifier que chaque équipe a le bon nombre de joueurs
    for team in teams:
        players = db.query(models.Player).filter(models.Player.team_id == team.id).count()
        if players != game.players_per_team:
            raise HTTPException(
                status_code=400, 
                detail=f"L'équipe {team.name} doit avoir {game.players_per_team} joueurs"
            )
    
    game.is_active = True
    game.started = True
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
    
    question = query.order_by(func.random()).first()
    
    if not question:
        raise HTTPException(status_code=404, detail="Aucune question trouvée")
    
    # Mélanger les réponses de façon déterministe (basé sur le question_id)
    # pour que l'ordre soit stable entre les appels de polling
    import json, hashlib
    wrong_answers = json.loads(question.wrong_answers) if question.wrong_answers else []
    options = wrong_answers + [question.correct_answer]
    # Seed basé sur le hash du question_id → ordre identique pour chaque équipe
    seed = int(hashlib.md5(str(question.id).encode()).hexdigest(), 16) % (2**32)
    rng = random.Random(seed)
    rng.shuffle(options)
    
    return {
        "question": question,
        "options": options
    }

@app.post("/games/{code}/set-current-question")
def set_current_question(code: str, request: schemas.SetCurrentQuestionRequest, db: Session = Depends(get_db), _host: models.GameSession = Depends(require_host)):
    """
    Définir la question courante pour toutes les équipes (synchronisation)
    """
    game = db.query(models.GameSession).filter(models.GameSession.code == code).first()
    if not game:
        raise HTTPException(status_code=404, detail="Session de jeu non trouvée")
    
    question = db.query(models.Question).filter(models.Question.id == request.question_id).first()
    if not question:
        raise HTTPException(status_code=404, detail="Question non trouvée")
    
    game.current_question_id = request.question_id
    db.commit()
    
    return {
        "message": "Question courante définie",
        "question": question.text,
        "question_id": question.id
    }

@app.get("/games/{code}/current-question")
def get_current_question(code: str, db: Session = Depends(get_db)):
    """
    Obtenir la question courante synchronisée pour toutes les équipes
    """
    game = db.query(models.GameSession).filter(models.GameSession.code == code).first()
    if not game:
        raise HTTPException(status_code=404, detail="Session de jeu non trouvée")
    
    if not game.current_question_id:
        return {"message": "Pas de question courante définie", "question_id": None}
    
    question = db.query(models.Question).filter(models.Question.id == game.current_question_id).first()
    
    if not question:
        raise HTTPException(status_code=404, detail="Question non trouvée")
    
    # Mélanger les réponses de façon déterministe (basé sur le question_id)
    # pour que l'ordre soit stable entre les appels de polling
    import json, hashlib
    wrong_answers = json.loads(question.wrong_answers) if question.wrong_answers else []
    options = wrong_answers + [question.correct_answer]
    # Seed basé sur le hash du question_id → ordre identique pour chaque équipe
    seed = int(hashlib.md5(str(question.id).encode()).hexdigest(), 16) % (2**32)
    rng = random.Random(seed)
    rng.shuffle(options)
    
    return {
        "question": question,
        "options": options,
        "question_id": question.id
    }

@app.get("/games/{code}/answers-status")
def get_answers_status(code: str, question_id: int = None, db: Session = Depends(get_db)):
    """
    Obtenir le statut des réponses pour la question courante
    """
    game = db.query(models.GameSession).filter(models.GameSession.code == code).first()
    if not game:
        raise HTTPException(status_code=404, detail="Session de jeu non trouvée")
    
    # Si question_id n'est pas fourni, utiliser la question courante
    if not question_id:
        question_id = game.current_question_id
        if not question_id:
            return {"message": "Pas de question courante définie", "answered": []}
    
    teams = db.query(models.Team).filter(models.Team.game_session_id == game.id).all()
    team_ids = [team.id for team in teams]
    
    # Obtenir les réponses déjà données pour cette question
    answered_teams = db.query(models.Answer).filter(
        models.Answer.question_id == question_id,
        models.Answer.team_id.in_(team_ids)
    ).all()
    
    # Dédupliquer: si une équipe a soumis plusieurs réponses, compter une seule fois
    answered_ids = list(set([answer.team_id for answer in answered_teams]))
    all_ids = [team.id for team in teams]
    remaining_ids = [id for id in all_ids if id not in answered_ids]
    
    return {
        "question_id": question_id,
        "total_teams": len(all_ids),
        "answered_teams": answered_ids,
        "remaining_teams": remaining_ids,
        "all_answered": len(answered_ids) == len(all_ids)
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

    is_correct = answer_create.player_answer.strip().lower() == question.correct_answer.strip().lower()

    # BUG-110 : upsert atomique sur la contrainte unique (question_id, team_id).
    # Chaque coéquipier peut soumettre/corriger la réponse d'équipe tant que
    # l'host n'a pas validé ; la clause WHERE rend le verrouillage post-validation
    # atomique lui aussi (pas de fenêtre de course entre lecture et écriture).
    stmt = sqlite_insert(models.Answer).values(
        question_id=answer_create.question_id,
        team_id=answer_create.team_id,
        player_answer=answer_create.player_answer,
        is_correct=is_correct,
        points_earned=0,
    ).on_conflict_do_update(
        index_elements=[models.Answer.question_id, models.Answer.team_id],
        set_={
            "player_answer": answer_create.player_answer,
            "is_correct": is_correct,
        },
        where=models.Answer.validated_at.is_(None),
    )
    db.execute(stmt)
    db.commit()

    existing = db.query(models.Answer).filter(
        models.Answer.question_id == answer_create.question_id,
        models.Answer.team_id == answer_create.team_id,
    ).first()
    locked = existing.validated_at is not None

    # Ne révéler is_correct/correct_answer qu'une fois la réponse verrouillée
    # (validée par l'host) — sinon la soumission étant rejouable à volonté,
    # ce serait un oracle permettant de deviner la bonne réponse.
    return {
        "is_correct": existing.is_correct if locked else None,
        "correct_answer": question.correct_answer if locked else None,
        "points_earned": existing.points_earned,
        "team_score": team.score,
        "pending_validation": not locked,
    }

@app.post("/games/{code}/validate-answers")
def validate_answers(code: str, db: Session = Depends(get_db), _host: models.GameSession = Depends(require_host)):
    """
    L'host valide les réponses de toutes les équipes pour la question courante.
    Attribue les points aux équipes qui ont répondu correctement.
    """
    game = db.query(models.GameSession).filter(models.GameSession.code == code).first()
    if not game:
        raise HTTPException(status_code=404, detail="Session de jeu non trouvée")
    
    if not game.current_question_id:
        raise HTTPException(status_code=400, detail="Pas de question courante à valider")
    
    question = db.query(models.Question).filter(models.Question.id == game.current_question_id).first()
    if not question:
        raise HTTPException(status_code=404, detail="Question non trouvée")
    
    # FIX: Only get answers from teams in THIS game session (not previous games)
    teams_in_game = db.query(models.Team).filter(models.Team.game_session_id == game.id).all()
    team_ids_in_game = [t.id for t in teams_in_game]
    
    answers = db.query(models.Answer).filter(
        models.Answer.question_id == game.current_question_id,
        models.Answer.team_id.in_(team_ids_in_game)
    ).all()
    
    # Attribuer les points pour chaque réponse correcte (idempotent — safe to call multiple times)
    teams_updated = []
    teams_processed = set()
    for answer in answers:
        if answer.team_id in teams_processed:
            continue
        teams_processed.add(answer.team_id)
        # Récupérer l'état le plus frais possible juste avant de calculer les
        # points : une soumission concurrente a pu modifier is_correct entre
        # le SELECT initial de cette fonction et ce point de la boucle.
        db.refresh(answer)
        answer.validated_at = func.now()
        team = db.query(models.Team).filter(models.Team.id == answer.team_id).first()
        if team and answer.is_correct and answer.points_earned == 0:
            points = award_points_with_bonus(team, question.points)
            team.score += points
            answer.points_earned = points
            teams_updated.append({
                "team_id": team.id,
                "team_name": team.name,
                "is_correct": True,
                "points_earned": points,
                "new_score": team.score,
            })
        elif team and answer.is_correct:
            # Already validated — return existing data without double-counting
            teams_updated.append({
                "team_id": team.id,
                "team_name": team.name,
                "is_correct": True,
                "points_earned": answer.points_earned,
                "new_score": team.score,
            })
        elif team:
            # Réponse fausse : pas de points, mais le bonus visait cette
            # question — il est tout de même consommé.
            team.bonus_active = False
            teams_updated.append({
                "team_id": team.id,
                "team_name": team.name,
                "is_correct": False,
                "points_earned": 0,
                "new_score": team.score,
            })
    
    db.commit()
    
    # Effacer la question courante (toutes les équipes ont été validées)
    game.current_question_id = None
    db.commit()
    
    return {
        "message": "Réponses validées avec succès",
        "teams_updated": teams_updated,
        "question_text": question.text,
        "correct_answer": question.correct_answer,
    }

@app.get("/teams/{team_id}/tokens")
def get_team_tokens(team_id: int, db: Session = Depends(get_db)):
    """
    Récupérer les jetons disponibles pour une équipe
    """
    tokens = db.query(models.Token).filter(
        models.Token.team_id == team_id,
        models.Token.is_used == False
    ).all()
    
    # CORRECTION : Renvoyer directement le tableau (la liste) attendu par le frontend
    return [
        {
            "id": token.id,
            "token_type": token.token_type.value,
            "is_used": token.is_used
        } for token in tokens
    ]


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
    memory_grid = manager.create_memory_grid(game.id, rows=7, cols=5)

    return memory_grid

@app.post("/games/{code}/memory-grid/start", response_model=schemas.StartMemoryGridRoundResponse)
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

@app.get("/memory-grid/{memory_grid_id}/state")
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

@app.post("/memory-grid/answer-cell")
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

@app.post("/memory-grid/{memory_grid_id}/skip-turn")
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

    # La cellule éventuellement révélée par le joueur dont le tour expire
    # redevient cachée : sinon le joueur suivant hériterait d'une question
    # déjà exposée gratuitement.
    revealed_cell = db.query(GridCell).filter(
        GridCell.memory_grid_id == memory_grid_id,
        GridCell.status == GridCellStatus.REVEALED
    ).first()
    if revealed_cell:
        revealed_cell.status = GridCellStatus.HIDDEN

    new_turn = manager.advance_turn(memory_grid_id)
    db.commit()

    return {"memory_grid_id": memory_grid_id, "current_turn": new_turn}

@app.post("/games/{code}/advance-to-phase3")
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
@app.post("/games/{code}/memory-grid/create-with-themes", response_model=schemas.MemoryGrid)
def create_memory_grid_with_themes(code: str, rows: int = 7, cols: int = 5, db: Session = Depends(get_db), _host: models.GameSession = Depends(require_host)):
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
    
    manager = MemoryGridManager(db)
    try:
        memory_grid = manager.create_memory_grid_with_themes(game.id, rows=rows, cols=cols)
        return memory_grid
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/games/{code}/memory-grid/finalists")
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

@app.post("/games/{code}/qualify-round2")
def qualify_players_from_round1(code: str, db: Session = Depends(get_db), _host: models.GameSession = Depends(require_host)):
    """
    Qualifier les 8 joueurs de la Manche 2 depuis les meilleures équipes.

    AD-0 : Manche 1 collective -> Manche 2 individuelle (8 joueurs).
    AD-7 : c'est cette transition qui pose enfin MANCHE_2.
    AD-5 : l'endpoint possède la transaction.
    """
    game = db.query(models.GameSession).filter(models.GameSession.code == code).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game session not found")

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


@app.get("/games/{code}/memory-grid/standings")
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

    memory_grid = db.query(MemoryGrid).filter(
        MemoryGrid.game_session_id == game.id
    ).order_by(MemoryGrid.id.desc()).first()
    if not memory_grid:
        raise HTTPException(status_code=404, detail="Aucune grille mémoire pour cette partie")

    try:
        return MemoryGridEnhancer(db).calculate_winner(memory_grid.id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/memory-grid/{memory_grid_id}/current-player-turn")
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

@app.get("/games/{code}/available-colors")
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

@app.post("/memory-grid/select-color")
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

# Round 2 Endpoints (16→8→4 Tournament)
@app.get("/round2/{game_code}/players")
def get_round2_qualified_players(game_code: str, db: Session = Depends(get_db)):
    """
    Liste des joueurs qualifiés pour la Manche 2 (ceux ayant une ligne
    PlayerRound2Stats pour cette partie), pour permettre à un appareil de se
    reconnecter sous SA véritable identité au lieu de créer un joueur libre
    non lié à la qualification de la Manche 1 (bug utilisateur).
    """
    game = db.query(models.GameSession).filter(models.GameSession.code == game_code).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game session not found")

    stats = db.query(models.PlayerRound2Stats).filter(
        models.PlayerRound2Stats.game_session_id == game.id
    ).all()
    player_ids = [s.player_id for s in stats]
    players = db.query(models.Player).filter(models.Player.id.in_(player_ids)).all()
    teams_by_id = {t.id: t for t in db.query(models.Team).filter(
        models.Team.id.in_([p.team_id for p in players if p.team_id])
    ).all()}

    return [
        {
            "id": p.id,
            "name": p.name,
            "team_id": p.team_id,
            "team_name": teams_by_id[p.team_id].name if p.team_id in teams_by_id else None,
        }
        for p in players
    ]

@app.get("/round2/{game_code}/themes")
def get_round2_themes(game_code: str, db: Session = Depends(get_db)):
    """
    Get 3 random themes for Round 2 selection
    """
    game = db.query(models.GameSession).filter(models.GameSession.code == game_code).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game session not found")
    
    manager = Round2Manager(db)
    themes = manager.get_available_themes(game.id, count=3)
    
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
def advance_round2_phase(game_code: str, db: Session = Depends(get_db), _host: models.GameSession = Depends(require_host_by_game_code)):
    """
    Advance to the next phase (16→8 or 8→4)
    """
    game = db.query(models.GameSession).filter(models.GameSession.code == game_code).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game session not found")
    
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

# Ping-Pong Duel Endpoints
@app.get("/ping-pong/random-theme", response_model=schemas.PingPongTheme)
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

@app.post("/ping-pong/duel/start", response_model=schemas.PingPongDuelResponse)
def start_ping_pong_duel(request: schemas.StartPingPongDuelRequest, db: Session = Depends(get_db)):
    """
    Démarrer un duel ping-pong entre 2 équipes.
    team1_id = équipe qui a tourné la roue (elle commence le duel).
    """
    from app.ping_pong_manager import PingPongManager
    
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

@app.post("/ping-pong/duel/answer", response_model=schemas.SubmitPingPongAnswerResponse)
def submit_ping_pong_duel_answer(request: schemas.SubmitPingPongAnswerRequest, db: Session = Depends(get_db)):
    """
    Soumettre une réponse dans un duel ping-pong.
    """
    from app.ping_pong_manager import PingPongManager
    
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
                resolve_manche1_end(db, game)

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

@app.get("/ping-pong/duel/{duel_id}")
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

@app.get("/ping-pong/duel/{duel_id}/results")
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

# Team-specific state endpoint (multi-screen architecture)
@app.get("/game/{code}/team/{team_id}/state")
def get_team_specific_state(code: str, team_id: int, db: Session = Depends(get_db)):
    """
    Retourne l'état spécifique à UNE équipe pour le jeu multi-écrans.
    
    Chaque équipe peut avoir son propre appareil et voir :
    - Si c'est son tour de répondre
    - La question courante (si elle n'a pas déjà répondu)
    - Les duels ping-pong en cours (si elle est impliquée)
    - Ses jetons disponibles
    - Son score actuel
    """
    game = db.query(models.GameSession).filter(models.GameSession.code == code).first()
    if not game:
        raise HTTPException(status_code=404, detail="Session de jeu non trouvée")

    # Récupérer l'équipe
    team = db.query(models.Team).filter(
        models.Team.id == team_id,
        models.Team.game_session_id == game.id,
    ).first()
    if not team:
        raise HTTPException(status_code=404, detail="Équipe non trouvée dans cette session")

    from app.ping_pong_manager import PingPongManager
    from app.round2_manager import Round2Manager

    # --- Statut de la question courante ---
    current_question_data = None
    has_answered = False
    answer_locked = False
    current_team_answer = None
    is_my_turn = True  # par défaut

    if game.current_question_id:
        question = db.query(models.Question).filter(
            models.Question.id == game.current_question_id
        ).first()

        if question:
            # Vérifier si cette équipe a déjà répondu à cette question.
            # BUG-110 : has_answered ne verrouille plus le formulaire tant que
            # l'host n'a pas validé — n'importe quel coéquipier peut corriger
            # la réponse jusque-là (answer_locked = réponse validée par l'host).
            existing_answer = db.query(models.Answer).filter(
                models.Answer.question_id == question.id,
                models.Answer.team_id == team_id,
            ).first()

            has_answered = existing_answer is not None
            answer_locked = existing_answer is not None and existing_answer.validated_at is not None
            current_team_answer = existing_answer.player_answer if existing_answer else None

            # Mélanger les réponses de façon déterministe (basé sur le question_id)
            # pour que l'ordre soit stable entre les appels de polling
            import json, hashlib
            wrong_answers = json.loads(question.wrong_answers) if question.wrong_answers else []
            options = wrong_answers + [question.correct_answer]
            # Seed basé sur le hash du question_id → ordre identique pour chaque équipe
            seed = int(hashlib.md5(str(question.id).encode()).hexdigest(), 16) % (2**32)
            rng = random.Random(seed)
            rng.shuffle(options)

            current_question_data = {
                "id": question.id,
                "text": question.text,
                "category": question.category,
                "difficulty": question.difficulty.value,
                "points": question.points,
                "correct_answer": question.correct_answer if answer_locked else None,  # Ne révéler qu'après validation host
                "options": options,
                "answer_locked": answer_locked,
                "current_team_answer": current_team_answer,
            }

    # Vérifier le statut des réponses pour déterminer si c'est le tour
    if game.current_question_id:
        teams_in_game = db.query(models.Team).filter(
            models.Team.game_session_id == game.id
        ).all()
        team_ids_in_game = [t.id for t in teams_in_game]

        answered_teams = db.query(models.Answer).filter(
            models.Answer.question_id == game.current_question_id,
            models.Answer.team_id.in_(team_ids_in_game),
        ).all()
        # Dédupliquer: une équipe peut avoir soumis plusieurs réponses
        answered_ids = list(set([a.team_id for a in answered_teams]))

        # Si toutes les équipes ont répondu, personne n'a "le tour"
        if len(answered_ids) == len(team_ids_in_game):
            is_my_turn = False

    # --- Duel Ping-Pong en cours ---
    ping_pong_manager = PingPongManager(db)
    active_duel_for_team = None

    # Chercher un duel actif où cette équipe est impliquée
    active_duel = db.query(models.PingPongDuel).filter(
        models.PingPongDuel.game_session_id == game.id,
        models.PingPongDuel.is_completed == False,
        models.PingPongDuel.team1_id == team_id,
    ).first()

    if not active_duel:
        active_duel = db.query(models.PingPongDuel).filter(
            models.PingPongDuel.game_session_id == game.id,
            models.PingPongDuel.is_completed == False,
            models.PingPongDuel.team2_id == team_id,
        ).first()

    if active_duel:
        try:
            duel_state = ping_pong_manager.get_duel_state(active_duel.id)
            active_duel_for_team = {
                "duel_id": active_duel.id,
                "theme": duel_state["theme"],
                "team1": duel_state["team1"],
                "team2": duel_state["team2"],
                "current_turn_team_id": duel_state["current_turn_team_id"],
                "current_turn_team_name": duel_state["current_turn_team_name"],
                "turn_number": duel_state["turn_number"],
                "answers_used": duel_state["answers_used"],
                "is_completed": duel_state["is_completed"],
                "winner_team_id": duel_state["winner_team_id"],
                "is_my_turn_in_duel": active_duel.current_turn_team_id == team_id,
            }
        except Exception:
            pass  # Duel not found or error — leave as None

    # --- Jetons ---
    tokens = db.query(models.Token).filter(
        models.Token.team_id == team_id,
        models.Token.is_used == False,
    ).all()

    tokens_data = [
        {"id": t.id, "token_type": t.token_type.value, "is_used": t.is_used}
        for t in tokens
    ]

    # --- Statut des autres équipes ---
    # Calculé indépendamment de la question courante : nécessaire pour cibler
    # une PENALTY ou choisir un adversaire de ping-pong même entre deux questions.
    teams_in_game = db.query(models.Team).filter(
        models.Team.game_session_id == game.id
    ).all()
    other_teams_status = []
    for t in teams_in_game:
        if t.id == team_id:
            continue
        other_teams_status.append({
            "team_id": t.id,
            "team_name": t.name,
            "team_score": t.score,
            "has_answered": t.id in answered_ids if game.current_question_id else False,
        })

    # Un host est désormais toujours présent (BUG-103) : la validation des
    # réponses est systématiquement manuelle, via /validate-answers.
    all_teams_answered = False
    validation_result_data = None

    if game.current_question_id:
        all_teams_answered = (
            len(answered_ids) == len(team_ids_in_game) and len(team_ids_in_game) > 0
        )

    # --- Dernier effet de roue (pour afficher un modal sur tous les écrans,
    # y compris ceux qui n'ont pas cliqué sur "Tour suivant") ---
    last_wheel_event = None
    latest_effect = db.query(models.WheelEffect).filter(
        models.WheelEffect.game_session_id == game.id
    ).order_by(models.WheelEffect.id.desc()).first()
    if latest_effect:
        target = db.query(models.Team).filter(models.Team.id == latest_effect.target_team_id).first()
        target_name = target.name if target else "?"
        if latest_effect.effect_type == "malus":
            message = f"💀 Malus : {target_name} perd {abs(latest_effect.value or 0)} points"
        elif latest_effect.effect_type == "bonus":
            message = f"🎉 Bonus : {target_name} gagne {latest_effect.value or 0} points"
        elif latest_effect.effect_type == "ping_pong":
            message = f"🏓 Duel Ping-Pong déclenché pour {target_name} !"
        elif latest_effect.effect_type == "tiebreak":
            message = f"⚖️ Égalité en fin de Manche 1 : duel de départage pour {target_name} !"
        else:
            message = "Effet de roue appliqué"
        last_wheel_event = {
            "id": latest_effect.id,
            "effect_type": latest_effect.effect_type,
            "value": latest_effect.value,
            "target_team_id": latest_effect.target_team_id,
            "target_team_name": target_name,
            "message": message,
        }

    return {
        "team_id": team_id,
        "team_name": team.name,
        "team_score": team.score,
        "game_session_id": game.id,
        "game_started": game.started,
        "game_phase": game.current_round.value,
        "is_my_turn": is_my_turn,
        "has_answered": has_answered,
        "answer_locked": answer_locked,
        "current_question": current_question_data,
        "active_duel": active_duel_for_team,
        "tokens": tokens_data,
        "other_teams": other_teams_status,
        "all_answered": all_teams_answered,
        "validation_result": validation_result_data,
        "last_wheel_event": last_wheel_event,
    }

def trigger_wheel_effect(db: Session, game: models.GameSession) -> Optional[dict]:
    """Fait tourner la roue automatiquement pour l'équipe dont c'est le tour
    (rotation déterministe sur `questions_played // 5`), applique l'effet en
    base et le journalise dans WheelEffect. Reprend les probabilités du jeu
    de plateau (1-5 malus, 6-10 +1, 11-18 ping-pong, 19-20 +3).
    """
    teams = db.query(models.Team).filter(models.Team.game_session_id == game.id).order_by(models.Team.id).all()
    if not teams:
        return None

    wheel_round = game.questions_played // 5
    spinning_team = teams[(wheel_round - 1) % len(teams)]

    spin_result = random.randint(1, 20)
    if spin_result <= 5:
        effect_type, value = "malus", -3
        spinning_team.score = max(0, spinning_team.score + value)
        message = f"💀 Malus : {spinning_team.name} perd 3 points"
    elif spin_result <= 10:
        # Mode sans hôte : le choix +1 point / récupération de jeton est
        # auto-résolu en +1 point (pas d'interface pour arbitrer ce choix).
        effect_type, value = "bonus", 1
        spinning_team.score += value
        message = f"🎉 {spinning_team.name} gagne 1 point"
    elif spin_result <= 18:
        effect_type, value = "ping_pong", None
        message = f"🏓 Duel Ping-Pong pour {spinning_team.name} !"
    else:
        effect_type, value = "bonus", 3
        spinning_team.score += value
        message = f"🎉 Bonus : {spinning_team.name} gagne 3 points !"

    if effect_type == "ping_pong" and not any(t.id != spinning_team.id for t in teams):
        # Une seule équipe en jeu : pas d'adversaire possible pour le duel.
        effect_type, value = "bonus", 2
        spinning_team.score += value
        message = f"Pas d'adversaire disponible pour le ping-pong : {spinning_team.name} reçoit +2 points à la place."
    elif effect_type == "ping_pong":
        # L'équipe qui tombe sur le ping-pong choisit elle-même son adversaire
        # (voir TeamScreen.tsx) — pas de duel démarré ici, juste l'annonce.
        message = f"🏓 {spinning_team.name}, choisissez votre adversaire !"

    wheel_effect = models.WheelEffect(
        game_session_id=game.id,
        effect_type=effect_type,
        value=value,
        target_team_id=spinning_team.id,
        is_applied=True,
    )
    db.add(wheel_effect)
    db.commit()
    db.refresh(wheel_effect)

    return {
        "id": wheel_effect.id,
        "effect_type": wheel_effect.effect_type,
        "value": wheel_effect.value,
        "target_team_id": spinning_team.id,
        "target_team_name": spinning_team.name,
        "duel_id": None,
        "message": message,
    }


def _pending_tiebreak_duel(db: Session, game: models.GameSession) -> Optional[models.PingPongDuel]:
    return db.query(models.PingPongDuel).filter(
        models.PingPongDuel.game_session_id == game.id,
        models.PingPongDuel.is_tiebreak == True,
        models.PingPongDuel.is_completed == False,
    ).first()


def resolve_manche1_end(db: Session, game: models.GameSession) -> dict:
    """Manche 1 vient d'atteindre son maximum de questions (ou un duel de
    départage vient de se terminer). Si le classement laisse une égalité
    gênante sur la dernière place qualificative pour la Manche 2, déclenche
    un duel ping-pong de départage entre les deux équipes concernées avant
    de qualifier. Sinon, qualifie directement pour la Manche 2.
    """
    from app.round2_manager import Round2Manager
    from app.ping_pong_manager import PingPongManager

    pending = _pending_tiebreak_duel(db, game)
    if pending:
        return {"status": "tiebreak_pending", "duel_id": pending.id}

    manager = Round2Manager(db)
    slots = manager.ROUND2_SLOTS

    teams = db.query(models.Team).filter(models.Team.game_session_id == game.id).all()
    teams_sorted = sorted(teams, key=lambda t: -t.score)

    remaining = slots
    boundary_team = None
    for t in teams_sorted:
        if remaining <= 0:
            break
        remaining -= len(t.players)
        boundary_team = t

    if boundary_team is not None:
        boundary_score = boundary_team.score
        tied_teams = [t for t in teams_sorted if t.score == boundary_score]
        higher_players = sum(len(t.players) for t in teams_sorted if t.score > boundary_score)
        tied_players_all = sum(len(t.players) for t in tied_teams)

        # Ambiguë seulement si ni "toutes les équipes à égalité qualifient"
        # ni "aucune ne qualifie" n'est possible sans dépasser la tolérance —
        # sinon le tri normal par score suffit déjà à trancher.
        if len(tied_teams) > 1 and higher_players < slots and higher_players + tied_players_all > slots + 1:
            team_a, team_b = tied_teams[0], tied_teams[1]
            pp_manager = PingPongManager(db)
            theme = pp_manager.get_random_theme()
            if theme:
                duel = pp_manager.start_duel(
                    game_session_id=game.id,
                    theme_id=theme.id,
                    team1_id=team_a.id,
                    team2_id=team_b.id,
                )
                duel.is_tiebreak = True
                db.add(models.WheelEffect(
                    game_session_id=game.id,
                    effect_type="tiebreak",
                    value=None,
                    target_team_id=team_a.id,
                    is_applied=True,
                ))
                db.commit()
                return {
                    "status": "tiebreak_started",
                    "duel_id": duel.id,
                    "team1_id": team_a.id,
                    "team2_id": team_b.id,
                }

    try:
        result = manager.qualify_players_from_round1(game.id)
        db.commit()
    except (LookupError, ValueError) as e:
        db.rollback()
        logger.warning("Fin de Manche 1 : qualification impossible pour %s : %s", game.code, e)
        return {"status": "qualification_failed", "detail": str(e)}

    return {"status": "qualified", **result}


@app.post("/games/{code}/next-question")
def next_question(code: str, db: Session = Depends(get_db), _host: models.GameSession = Depends(require_host)):
    """
    Passer à la question suivante (utilisable sans hôte).
    Choisit une question aléatoire et la définit comme question courante —
    sauf tous les 5 tours (roue de fortune), ou au-delà de
    MANCHE_1_MAX_QUESTIONS où la Manche 1 se termine à la place.
    """
    game = db.query(models.GameSession).filter(models.GameSession.code == code).first()
    if not game:
        raise HTTPException(status_code=404, detail="Session de jeu non trouvée")

    if game.current_round == models.RoundType.MANCHE_1 and _pending_tiebreak_duel(db, game):
        # Un duel de départage de fin de Manche 1 est en cours : on ne
        # touche à rien tant qu'il n'est pas résolu (voir submit_ping_pong_duel_answer).
        return {
            "message": "Un duel de départage est en cours, patientez.",
            "question_id": None,
        }

    game.questions_played = (game.questions_played or 0) + 1
    db.commit()

    if game.current_round == models.RoundType.MANCHE_1 and game.questions_played >= MANCHE_1_MAX_QUESTIONS:
        outcome = resolve_manche1_end(db, game)
        return {
            "message": "Manche 1 terminée !",
            "question_id": None,
            "manche1_end": outcome,
        }

    if game.questions_played % 5 == 0:
        wheel_event = trigger_wheel_effect(db, game)
        game.current_question_id = None
        db.commit()
        return {
            "message": "C'est l'heure de la roue de fortune !",
            "question_id": None,
            "wheel_event": wheel_event,
        }

    # Choisir une question aléatoire
    question = db.query(models.Question).order_by(func.random()).first()
    if not question:
        raise HTTPException(status_code=404, detail="Aucune question disponible")

    # Définir comme question courante
    game.current_question_id = question.id
    db.commit()

    return {
        "message": "Nouvelle question définie",
        "question_id": question.id,
        "question_text": question.text,
    }


@app.post("/tokens/use")
def use_token(data: dict, db: Session = Depends(get_db)):
    team_id = data.get("team_id")
    target_team_id = data.get("target_team_id")
    token_type = data.get("token_type", "").upper()  # Ex: "SWAP", "PENALTY", "BONUS"

    # Le jeton PENALTY cible une équipe adverse précise : on valide la cible
    # avant de consommer le jeton, pour ne pas le perdre sur une requête invalide.
    target_team = None
    if token_type == "PENALTY":
        if not target_team_id:
            raise HTTPException(status_code=400, detail="Une équipe cible est requise pour utiliser un jeton PENALTY")
        team = db.query(models.Team).filter(models.Team.id == team_id).first()
        if not team:
            raise HTTPException(status_code=404, detail="Équipe non trouvée")
        if target_team_id == team_id:
            raise HTTPException(status_code=400, detail="Impossible de cibler sa propre équipe")
        target_team = db.query(models.Team).filter(
            models.Team.id == target_team_id,
            models.Team.game_session_id == team.game_session_id,
        ).first()
        if not target_team:
            raise HTTPException(status_code=404, detail="Équipe cible non trouvée dans cette partie")

    # Consomme le jeton via un UPDATE conditionnel (WHERE id=... AND
    # is_used=False), et vérifie le nombre de lignes modifiées, plutôt qu'un
    # SELECT suivi d'une écriture séparée sur l'objet en mémoire. Portable
    # SQLite/PostgreSQL — contrairement à SELECT ... FOR UPDATE, qui est un
    # no-op silencieux sur SQLite (le moteur utilisé en production ici) et ne
    # protégeait donc pas réellement contre la course entre deux requêtes
    # concurrentes sur le même jeton (ex. deux coéquipiers cliquant SWAP au
    # même moment), cause de BUG-101 : "swaps infinis". L'UPDATE lui-même
    # sérialise les écritures concurrentes ; seule l'une d'elles peut modifier
    # une ligne encore à is_used=False, l'autre affecte 0 ligne.
    candidate_token = db.query(models.Token).filter(
        models.Token.team_id == team_id,
        models.Token.token_type == token_type,
        models.Token.is_used == False
    ).first()

    chosen_token = None
    if candidate_token:
        rows_updated = db.query(models.Token).filter(
            models.Token.id == candidate_token.id,
            models.Token.is_used == False
        ).update({"is_used": True}, synchronize_session=False)
        if rows_updated:
            candidate_token.is_used = True
            chosen_token = candidate_token

    # Si le jeton de ce type existe et était disponible, on applique son effet
    if chosen_token:
        penalized_teams = []
        if token_type == "PENALTY" and target_team:
            # Retire des points à l'équipe ciblée uniquement (score plancher à 0).
            target_team.score = max(0, target_team.score - PENALTY_POINTS)
            penalized_teams.append({"team_id": target_team.id, "new_score": target_team.score})
        elif token_type == "BONUS":
            # Consommé à la prochaine validation de réponse de cette équipe (voir validate_answers).
            team = db.query(models.Team).filter(models.Team.id == team_id).first()
            if team:
                team.bonus_active = True
        elif token_type == "SWAP":
            # En duel ping-pong : change le thème du duel (le jeton ne
            # touchait jusqu'ici que la question de Manche 1, jamais le
            # thème d'un duel en cours — bug utilisateur). Sinon : change la
            # question courante de la partie.
            active_duel = db.query(models.PingPongDuel).filter(
                models.PingPongDuel.is_completed == False,
                or_(
                    models.PingPongDuel.team1_id == team_id,
                    models.PingPongDuel.team2_id == team_id,
                ),
            ).first()
            if active_duel:
                new_theme = db.query(models.PingPongTheme).filter(
                    models.PingPongTheme.id != active_duel.theme_id
                ).order_by(func.random()).first()
                if new_theme:
                    active_duel.theme_id = new_theme.id
                    active_duel.answers_used = []
            else:
                team = db.query(models.Team).filter(models.Team.id == team_id).first()
                game = db.query(models.GameSession).filter(
                    models.GameSession.id == team.game_session_id
                ).first() if team else None
                if game and game.current_question_id:
                    new_question = db.query(models.Question).filter(
                        models.Question.id != game.current_question_id
                    ).order_by(func.random()).first()
                    if new_question:
                        game.current_question_id = new_question.id

        db.commit()
        return {
            "status": "success",
            "message": f"Jeton {token_type} consommé avec succès.",
            "token_type": token_type,
            "penalized_teams": penalized_teams,
        }

    # S'il n'existe pas ou a déjà été utilisé
    raise HTTPException(
        status_code=400,
        detail=f"Jeton {token_type} non disponible ou déjà utilisé !"
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

