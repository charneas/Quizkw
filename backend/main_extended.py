"""
Extensions d'endpoints pour Memory Grid - Round 3
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.memory_grid import MemoryGridManager, MemoryGrid, GridCell, MemoryGridRound
from app.memory_grid_enhanced import MemoryGridEnhancer, PlayerColor
from app.schemas_extended import (
    ColorSelectionRequest, ColorSelectionResponse,
    ThemeSelectionRequest, ThemeSelectionResponse,
    ColorPaletteResponse, ThemePaletteResponse,
    MemoryGridDetailedStateResponse, GameResultResponse,
    RoundInfoResponse, TurnAdvanceResponse,
    PlayerSetupStatusResponse, PlayerColorEnum
)

router = APIRouter(prefix="/memory-grid", tags=["Memory Grid Round 3"])

# Round 3 Memory Grid Enhanced Endpoints

@router.post("/color/select", response_model=ColorSelectionResponse)
def select_player_color(request: ColorSelectionRequest, db: Session = Depends(get_db)):
    """
    Sélectionner une couleur unique pour un joueur dans Round 3.
    """
    enhancer = MemoryGridEnhancer(db)
    
    try:
        result = enhancer.select_player_color(
            player_id=request.player_id,
            game_session_id=request.game_session_id,
            color=request.color
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la sélection de couleur: {str(e)}")

@router.post("/theme/select", response_model=ThemeSelectionResponse)
def select_player_themes(request: ThemeSelectionRequest, db: Session = Depends(get_db)):
    """
    Sélectionner 3 thèmes uniques pour un joueur dans Round 3.
    """
    enhancer = MemoryGridEnhancer(db)
    
    try:
        result = enhancer.select_themes_for_player(
            player_id=request.player_id,
            game_session_id=request.game_session_id,
            theme_ids=request.theme_ids
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la sélection de thèmes: {str(e)}")

@router.get("/colors/available/{game_session_id}", response_model=ColorPaletteResponse)
def get_available_colors(game_session_id: int, db: Session = Depends(get_db)):
    """
    Obtenir la palette de couleurs disponibles pour une session.
    """
    enhancer = MemoryGridEnhancer(db)
    
    try:
        available_colors = enhancer.get_available_colors(game_session_id)
        
        # Pour l'instant, on retourne toutes les couleurs disponibles
        # Dans une implémentation complète, on calculerait les couleurs prises
        return ColorPaletteResponse(
            available_colors=[PlayerColorEnum(color) for color in available_colors],
            taken_colors={}  # À implémenter
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la récupération des couleurs: {str(e)}")

@router.get("/themes/available/{game_session_id}", response_model=ThemePaletteResponse)
def get_available_themes(game_session_id: int, db: Session = Depends(get_db)):
    """
    Obtenir 15 thèmes disponibles pour la sélection.
    """
    # Vérifier que la session existe
    game_session = db.query(models.GameSession).filter(models.GameSession.id == game_session_id).first()
    if not game_session:
        raise HTTPException(status_code=404, detail="Session de jeu non trouvée")
    
    enhancer = MemoryGridEnhancer(db)
    
    try:
        themes = enhancer.get_available_themes_for_selection(count=15)
        
        theme_data = []
        for theme in themes:
            theme_data.append({
                "id": theme.id,
                "name": theme.name,
                "category": theme.category.value if hasattr(theme.category, 'value') else str(theme.category),
                "difficulty_level": theme.difficulty_level,
                "description": theme.description
            })
        
        return ThemePaletteResponse(
            available_themes=theme_data,
            count=len(theme_data),
            message=f"{len(theme_data)} thèmes disponibles pour la sélection"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la récupération des thèmes: {str(e)}")

@router.get("/{memory_grid_id}/round-info", response_model=RoundInfoResponse)
def get_round_info(memory_grid_id: int, db: Session = Depends(get_db)):
    """
    Obtenir les informations sur le round actuel (1-5) de la grille mémoire.
    """
    enhancer = MemoryGridEnhancer(db)
    
    try:
        round_info = enhancer.get_current_round_info(memory_grid_id)
        return RoundInfoResponse(**round_info)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la récupération des informations du round: {str(e)}")

@router.post("/{memory_grid_id}/advance-turn", response_model=TurnAdvanceResponse)
def advance_turn(memory_grid_id: int, db: Session = Depends(get_db)):
    """
    Passer au tour suivant dans la grille mémoire.
    """
    enhancer = MemoryGridEnhancer(db)
    
    try:
        result = enhancer.advance_turn(memory_grid_id)
        return TurnAdvanceResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de l'avancement du tour: {str(e)}")

@router.get("/{memory_grid_id}/winner", response_model=GameResultResponse)
def calculate_winner(memory_grid_id: int, db: Session = Depends(get_db)):
    """
    Calculer le vainqueur de la grille mémoire.
    """
    enhancer = MemoryGridEnhancer(db)
    
    try:
        result = enhancer.calculate_winner(memory_grid_id)
        return GameResultResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors du calcul du vainqueur: {str(e)}")

@router.get("/player/{player_id}/setup-status/{game_session_id}", response_model=PlayerSetupStatusResponse)
def get_player_setup_status(player_id: int, game_session_id: int, db: Session = Depends(get_db)):
    """
    Obtenir le statut de setup d'un joueur (couleur + thèmes sélectionnés).
    """
    # Vérifier que le joueur existe
    player = db.query(models.Player).filter(models.Player.id == player_id).first()
    if not player:
        raise HTTPException(status_code=404, detail="Joueur non trouvé")
    
    # Vérifier que la session existe
    game_session = db.query(models.GameSession).filter(models.GameSession.id == game_session_id).first()
    if not game_session:
        raise HTTPException(status_code=404, detail="Session de jeu non trouvée")
    
    # Pour l'instant, retourner un statut par défaut
    # Dans une implémentation complète, on vérifierait dans la base de données
    return PlayerSetupStatusResponse(
        player_id=player_id,
        color_selected=False,
        themes_selected=False,
        selected_color=None,
        selected_themes=None,
        setup_complete=False
    )

@router.get("/{memory_grid_id}/detailed-state", response_model=MemoryGridDetailedStateResponse)
def get_detailed_memory_grid_state(memory_grid_id: int, db: Session = Depends(get_db)):
    """
    Obtenir l'état détaillé de la grille mémoire.
    """
    manager = MemoryGridManager(db)
    
    try:
        grid_state = manager.get_grid_state(memory_grid_id)
        if not grid_state:
            raise HTTPException(status_code=404, detail="Grille mémoire non trouvée")
        
        # Convertir le format existant vers le format détaillé
        memory_grid_info = grid_state["memory_grid"]
        cells_info = []
        
        for cell in grid_state["cells"]:
            cell_info = {
                "id": cell["id"],
                "row": cell["row"],
                "col": cell["col"],
                "status": cell["status"],
                "assigned_team_id": cell["assigned_team_id"],
                "answered_by_team_id": cell["answered_by_team_id"],
                "question": cell.get("question")
            }
            cells_info.append(cell_info)
        
        # Déterminer le round actuel
        enhancer = MemoryGridEnhancer(db)
        round_info = enhancer.get_current_round_info(memory_grid_id)
        
        return MemoryGridDetailedStateResponse(
            memory_grid_id=memory_grid_info["id"],
            rows=memory_grid_info["rows"],
            cols=memory_grid_info["cols"],
            current_turn=memory_grid_info["current_turn"],
            is_completed=memory_grid_info["is_completed"],
            cells=cells_info,
            current_team_id=None,  # À implémenter
            current_round=round_info["current_round"]
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la récupération de l'état détaillé: {str(e)}")
    
from fastapi import HTTPException, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app import models

@router.post("/tokens/use")
def use_token_extended(data: dict, db: Session = Depends(get_db)):
    """
    Mode Utilisateur Strict injecté dans le routeur principal.
    """
    team_id = data.get("team_id")
    token_type_raw = data.get("token_type", "SWAP")
    
    try:
        val_str = str(token_type_raw).upper().strip()
    except:
        val_str = "SWAP"

    # 1. Recherche d'un jeton non utilisé pour cette équipe
    chosen_token = db.query(models.Token).filter(
        models.Token.team_id == team_id,
        models.Token.is_used == False
    ).first()

    # 2. Si trouvé, on le consomme
    if chosen_token:
        chosen_token.is_used = True
        db.commit()
        print(f"🎮 [Router] Jeton {val_str} consommé pour l'équipe {team_id}")
        return {
            "status": "success", 
            "message": f"Jeton {val_str} consommé.", 
            "token_id": chosen_token.id
        }
    
    # 3. Si aucun jeton disponible, on renvoie un refus strict (400)
    print(f"🛑 [Router] Refus : Plus de jetons pour l'équipe {team_id}")
    raise HTTPException(
        status_code=400, 
        detail="Jeton non disponible. Vous avez épuisé vos jetons !"
    )

from fastapi import HTTPException, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app import models

@router.post("/tokens/use")
def use_token_extended(data: dict, db: Session = Depends(get_db)):
    team_id = data.get("team_id")
    token_type_raw = data.get("token_type", "SWAP")
    
    # 1. On cherche si CETTE équipe a un jeton encore disponible (is_used == False)
    chosen_token = db.query(models.Token).filter(
        models.Token.team_id == team_id,
        models.Token.is_used == False
    ).first()

    # 2. Si le jeton existe et est disponible, on le consomme (is_used = True)
    if chosen_token:
        chosen_token.is_used = True
        db.commit()
        return {
            "status": "success", 
            "message": "Jeton consommé avec succès.", 
            "token_id": chosen_token.id
        }
    
    # 3. S'il n'y en a plus : ON BLOQUE L'ÉQUIPE (Erreur 400)
    raise HTTPException(
        status_code=400, 
        detail="Jeton non disponible. Vous avez déjà utilisé votre jeton !"
    )