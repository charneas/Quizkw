"""
Schémas Pydantic pour la génération semi-automatique de contenu (Epic F, story F.2).

AD-13 : un contrat par concept. Les schémas de Theme/Question réels restent dans
app/schemas.py — ici seulement les concepts propres à F.2 (suggestion, flag, historique).
"""
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

from app.schemas import ThemeCategoryEnum, DifficultyEnum

# Mix cible du contenu, en pourcentage (AC #3, epics-and-stories.md § Épic F).
TARGET_CATEGORY_MIX = {
    ThemeCategoryEnum.serious: 0.5,
    ThemeCategoryEnum.pop_culture: 0.3,
    ThemeCategoryEnum.whimsical: 0.2,
}


class GeneratedQuestion(BaseModel):
    """Une question telle que produite par le LLM, avant tout écriture en base.
    Mêmes contraintes que schemas.QuestionCreate (AD-13 : même concept)."""
    text: str
    correct_answer: str
    wrong_answers: List[str] = Field(..., min_length=1)
    difficulty: DifficultyEnum


class GeneratedContent(BaseModel):
    """Forme strictement attendue de la réponse JSON du LLM. Utilisé pour valider
    la sortie de Claude avant persistance — un JSON qui ne correspond pas à ce
    contrat fait échouer la génération (502), jamais une suggestion à moitié
    remplie (voir Dev Notes de la story, AD-6)."""
    theme_name: str
    category: ThemeCategoryEnum
    questions: List[GeneratedQuestion] = Field(..., min_length=1)


class GenerateContentRequest(BaseModel):
    topic: str
    category: Optional[ThemeCategoryEnum] = None


class ContentSuggestionResponse(BaseModel):
    id: int
    topic: str
    wikipedia_extract: str
    generated_theme_name: str
    generated_category: ThemeCategoryEnum
    generated_questions: List[GeneratedQuestion]
    status: str
    created_at: datetime
    reviewed_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    created_theme_id: Optional[int] = None

    class Config:
        from_attributes = True


class ApproveSuggestionResponse(BaseModel):
    suggestion_id: int
    theme_id: int
    questions_created: int
    message: str


class RejectSuggestionRequest(BaseModel):
    reason: str


class RejectSuggestionResponse(BaseModel):
    suggestion_id: int
    message: str


class CategoryMixEntry(BaseModel):
    category: ThemeCategoryEnum
    current_count: int
    current_ratio: float
    target_ratio: float


class CategoryMixResponse(BaseModel):
    total_themes: int
    mix: List[CategoryMixEntry]
    recommended_category: ThemeCategoryEnum


class FlagQuestionRequest(BaseModel):
    reason: str


class FlagQuestionResponse(BaseModel):
    flag_id: int
    question_id: int
    message: str


class ContentFlagResponse(BaseModel):
    id: int
    question_id: int
    reason: str
    flagged_at: datetime
    resolved: bool
    resolved_at: Optional[datetime] = None
    resolution_note: Optional[str] = None

    class Config:
        from_attributes = True


class ResolveFlagRequest(BaseModel):
    note: Optional[str] = None


class ContentHistoryEntry(BaseModel):
    id: int
    entity_type: str
    entity_id: int
    action: str
    detail: Optional[str] = None
    actor: str
    created_at: datetime

    class Config:
        from_attributes = True
