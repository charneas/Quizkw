"""
Schémas Pydantic pour l'interface d'administration de contenu (Epic F, story F.1).

AD-13 : un contrat par concept, nommé et exporté ici plutôt que redéclaré
inline dans le router ou côté client.
"""
from pydantic import BaseModel, Field
from typing import List, Optional

from app.schemas import Theme, ThemeCreate, Question, QuestionCreate, ThemeCategoryEnum, DifficultyEnum

# Seuil minimum de questions par thème pour qu'un thème soit "utilisable" en jeu
# (voir Story F.1, AC #3 et epics-and-stories.md § Épic F).
MIN_QUESTIONS_PER_THEME = 10

# AC #2 : Easy/Medium/Hard -> 2/4/6 points. Utilisé pour garder points et
# difficulté synchronisés quand seule la difficulté est mise à jour (revue
# de code : un PUT changeant difficulty sans points désynchronisait les deux
# silencieusement, sans aucun moyen de le corriger ensuite).
DIFFICULTY_POINTS = {"easy": 2, "medium": 4, "hard": 6}


class ThemeUpdate(BaseModel):
    """Champs modifiables d'un thème existant (tous optionnels)."""
    name: Optional[str] = None
    category: Optional[ThemeCategoryEnum] = None
    difficulty_level: Optional[int] = Field(None, ge=1, le=10)
    description: Optional[str] = None


class QuestionUpdate(BaseModel):
    """Champs modifiables d'une question existante (tous optionnels)."""
    text: Optional[str] = None
    category: Optional[str] = None
    difficulty: Optional[DifficultyEnum] = None
    points: Optional[int] = Field(None, ge=2, le=6)
    correct_answer: Optional[str] = None
    wrong_answers: Optional[List[str]] = None
    theme_id: Optional[int] = None
    question_number: Optional[int] = Field(None, ge=1, le=10)
    image_url: Optional[str] = None


class ThemeDeleteWarning(BaseModel):
    """Avertissement retourné lorsqu'une opération fait passer un thème sous le seuil de cohérence,
    ou (suppression du thème lui-même) que ses questions deviennent orphelines."""
    theme_id: int
    theme_name: str
    question_count: int
    message: str


class ThemeDeleteResponse(BaseModel):
    deleted_theme_id: int
    warning: Optional[ThemeDeleteWarning] = None
    message: str


class QuestionDeleteResponse(BaseModel):
    deleted_question_id: int
    warning: Optional[ThemeDeleteWarning] = None
    message: str


class ContentExport(BaseModel):
    """Payload d'export/import de contenu (thèmes + questions)."""
    themes: List[Theme]
    questions: List[Question]


class ThemeImportEntry(ThemeCreate):
    """Un thème à importer, avec son id source optionnel.

    `source_id` n'est jamais persisté : il sert uniquement à remapper, dans
    le même payload, les `theme_id` des questions vers l'id réellement
    attribué en base (les thèmes importés reçoivent toujours un nouvel id).
    Sans ce remappage, un export puis réimport rattachait les questions à
    l'ancien id de thème, périmé (trouvé en revue de code).
    """
    source_id: Optional[int] = None


class ContentImportRequest(BaseModel):
    themes: List[ThemeImportEntry] = []
    questions: List[QuestionCreate] = []


class ContentImportResponse(BaseModel):
    themes_created: int
    questions_created: int
    message: str


class QuestionStatsResponse(BaseModel):
    question_id: int
    times_answered: int
    correct_answers: int
    success_rate: float

class QuestionStatsListItem(BaseModel):
    """Une ligne de /admin/stats/questions : stats agrégées + contexte
    (texte, thème) pour éviter un aller-retour par question côté front."""
    question_id: int
    text: str
    theme_id: Optional[int] = None
    theme_name: Optional[str] = None
    times_answered: int
    correct_answers: int
    success_rate: float

class ThemeStatsResponse(BaseModel):
    """Une ligne de /admin/stats/themes : stats agrégées sur toutes les
    questions du thème."""
    theme_id: int
    theme_name: str
    questions_count: int
    times_answered: int
    correct_answers: int
    success_rate: float
