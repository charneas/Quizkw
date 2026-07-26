"""
Router d'administration de contenu (Epic F, story F.1) : CRUD thèmes/questions,
validation de cohérence, export/import, statistiques d'utilisation.

Pas d'authentification (délibéré, voir Dev Notes de la story F.1 et la spine
d'architecture § Deferred : l'identité/auth est différée jusqu'à l'epic F et
reste hors scope de cette story — cohérent avec le reste de l'API aujourd'hui).
"""
import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.schemas_admin import (
    ThemeUpdate, QuestionUpdate,
    ThemeDeleteWarning, ThemeDeleteResponse, QuestionDeleteResponse,
    ContentExport, ContentImportRequest, ContentImportResponse,
    QuestionStatsResponse, MIN_QUESTIONS_PER_THEME, DIFFICULTY_POINTS,
)

router = APIRouter(prefix="/admin", tags=["Admin"])


def _theme_or_404(db: Session, theme_id: int) -> models.Theme:
    theme = db.query(models.Theme).filter(models.Theme.id == theme_id).first()
    if not theme:
        raise HTTPException(status_code=404, detail="Thème non trouvé")
    return theme


def _question_or_404(db: Session, question_id: int) -> models.Question:
    question = db.query(models.Question).filter(models.Question.id == question_id).first()
    if not question:
        raise HTTPException(status_code=404, detail="Question non trouvée")
    return question


def _theme_exists_or_404(db: Session, theme_id: int | None) -> None:
    """AD-6 : une référence à un thème inexistant est une 404 métier, pas un succès silencieux."""
    if theme_id is None:
        return
    if not db.query(models.Theme.id).filter(models.Theme.id == theme_id).first():
        raise HTTPException(status_code=404, detail=f"Thème {theme_id} non trouvé")


def _commit_or_400(db: Session) -> None:
    """AD-5 : l'endpoint possède la transaction et roule en arrière sur le chemin d'exception."""
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail="Contrainte violée (doublon ou référence invalide).") from e


def _flush_or_400(db: Session) -> None:
    """Comme _commit_or_400, mais pour un flush intermédiaire (ex. avant de logger
    un ContentHistory qui a besoin de l'id auto-généré) : une contrainte violée au
    flush doit aussi devenir un 400, pas fuiter comme une IntegrityError brute
    (trouvé en revue de code : ajouter un flush avant commit sans ce garde
    contournait _commit_or_400 et faisait remonter un 500 sur un thème dupliqué)."""
    try:
        db.flush()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail="Contrainte violée (doublon ou référence invalide).") from e


def _question_count_for_theme(db: Session, theme_id: int) -> int:
    return db.query(models.Question).filter(models.Question.theme_id == theme_id).count()


def _log_history(db: Session, entity_type: str, entity_id: int, action: str, detail: str | None = None) -> None:
    """AC #5 (story F.2) : journaliser aussi les écritures F.1, pas seulement les
    nouvelles routes — sinon l'historique serait incomplet dès le premier jour."""
    db.add(models.ContentHistory(entity_type=entity_type, entity_id=entity_id, action=action, detail=detail))


def _below_threshold_warning(db: Session, theme: models.Theme) -> ThemeDeleteWarning | None:
    """AC #3 : avertissement (non bloquant) si le thème passe sous le seuil de cohérence."""
    count = _question_count_for_theme(db, theme.id)
    if count < MIN_QUESTIONS_PER_THEME:
        return ThemeDeleteWarning(
            theme_id=theme.id,
            theme_name=theme.name,
            question_count=count,
            message=(
                f"Le thème '{theme.name}' n'a plus que {count} question(s), "
                f"sous le seuil de {MIN_QUESTIONS_PER_THEME} requis pour être utilisable en jeu."
            ),
        )
    return None


# --- Thèmes ---

@router.get("/themes", response_model=list[schemas.Theme])
def list_themes(db: Session = Depends(get_db)):
    return db.query(models.Theme).order_by(models.Theme.id).all()


@router.get("/themes/{theme_id}", response_model=schemas.Theme)
def get_theme(theme_id: int, db: Session = Depends(get_db)):
    return _theme_or_404(db, theme_id)


@router.post("/themes", response_model=schemas.Theme)
def create_theme(theme_create: schemas.ThemeCreate, db: Session = Depends(get_db)):
    data = theme_create.model_dump()
    data["category"] = models.ThemeCategory(data["category"])
    theme = models.Theme(**data)
    db.add(theme)
    _flush_or_400(db)
    _log_history(db, "theme", theme.id, "created", theme.name)
    _commit_or_400(db)
    db.refresh(theme)
    return theme


@router.put("/themes/{theme_id}", response_model=schemas.Theme)
def update_theme(theme_id: int, theme_update: ThemeUpdate, db: Session = Depends(get_db)):
    theme = _theme_or_404(db, theme_id)
    updates = theme_update.model_dump(exclude_unset=True)
    if "category" in updates and updates["category"] is not None:
        updates["category"] = models.ThemeCategory(updates["category"])
    for field, value in updates.items():
        setattr(theme, field, value)
    _log_history(db, "theme", theme.id, "updated", ", ".join(updates.keys()))
    _commit_or_400(db)
    db.refresh(theme)
    return theme


@router.delete("/themes/{theme_id}", response_model=ThemeDeleteResponse)
def delete_theme(theme_id: int, db: Session = Depends(get_db)):
    theme = _theme_or_404(db, theme_id)
    theme_name = theme.name
    # Compté AVANT suppression : Theme.questions (models.py) n'a ni cascade ni
    # passive_deletes, donc supprimer le thème détache ses questions
    # (theme_id -> NULL) au lieu de les supprimer. C'est le cas qui doit être
    # signalé, quel que soit le nombre de questions restantes (trouvé en revue
    # de code : l'ancienne version n'avertissait que si ce nombre était déjà
    # sous le seuil, ratant justement le cas le plus destructeur).
    question_count = _question_count_for_theme(db, theme_id)

    db.delete(theme)
    _log_history(db, "theme", theme_id, "deleted", theme_name)
    _commit_or_400(db)

    warning = None
    message = "Thème supprimé."
    if question_count > 0:
        warning = ThemeDeleteWarning(
            theme_id=theme_id,
            theme_name=theme_name,
            question_count=question_count,
            message=(
                f"Le thème '{theme_name}' avait {question_count} question(s) associée(s) : "
                "elles ne sont plus rattachées à aucun thème."
            ),
        )
        message = warning.message

    return ThemeDeleteResponse(deleted_theme_id=theme_id, warning=warning, message=message)


# --- Questions ---

@router.get("/questions", response_model=list[schemas.Question])
def list_questions(theme_id: int | None = None, db: Session = Depends(get_db)):
    query = db.query(models.Question)
    if theme_id is not None:
        query = query.filter(models.Question.theme_id == theme_id)
    return query.order_by(models.Question.id).all()


@router.get("/questions/{question_id}", response_model=schemas.Question)
def get_question(question_id: int, db: Session = Depends(get_db)):
    return _question_or_404(db, question_id)


@router.post("/questions", response_model=schemas.Question)
def create_question(question_create: schemas.QuestionCreate, db: Session = Depends(get_db)):
    _theme_exists_or_404(db, question_create.theme_id)
    data = question_create.model_dump()
    data["wrong_answers"] = json.dumps(data["wrong_answers"])
    data["difficulty"] = models.Difficulty(data["difficulty"])
    question = models.Question(**data)
    db.add(question)
    _flush_or_400(db)
    _log_history(db, "question", question.id, "created", question.text[:100])
    _commit_or_400(db)
    db.refresh(question)
    return question


@router.put("/questions/{question_id}", response_model=schemas.Question)
def update_question(question_id: int, question_update: QuestionUpdate, db: Session = Depends(get_db)):
    question = _question_or_404(db, question_id)
    updates = question_update.model_dump(exclude_unset=True)

    if "theme_id" in updates and updates["theme_id"] is not None:
        _theme_exists_or_404(db, updates["theme_id"])
    if "wrong_answers" in updates and updates["wrong_answers"] is not None:
        updates["wrong_answers"] = json.dumps(updates["wrong_answers"])
    if "difficulty" in updates and updates["difficulty"] is not None:
        # AC #2 : Easy/Medium/Hard -> 2/4/6 points. Si la difficulté change sans que
        # `points` soit fourni explicitement, on les resynchronise plutôt que de
        # laisser les deux diverger silencieusement (trouvé en revue de code :
        # aucune route ne permettait de rattraper cette divergence par la suite).
        if "points" not in updates or updates["points"] is None:
            updates["points"] = DIFFICULTY_POINTS[updates["difficulty"]]
        updates["difficulty"] = models.Difficulty(updates["difficulty"])

    for field, value in updates.items():
        setattr(question, field, value)
    _log_history(db, "question", question.id, "updated", ", ".join(updates.keys()))
    _commit_or_400(db)
    db.refresh(question)
    return question


@router.delete("/questions/{question_id}", response_model=QuestionDeleteResponse)
def delete_question(question_id: int, db: Session = Depends(get_db)):
    question = _question_or_404(db, question_id)
    theme_id = question.theme_id
    theme = db.query(models.Theme).filter(models.Theme.id == theme_id).first() if theme_id else None
    db.delete(question)
    _log_history(db, "question", question_id, "deleted", question.text[:100])
    _commit_or_400(db)

    warning = None
    if theme:
        warning = _below_threshold_warning(db, theme)

    message = "Question supprimée."
    if warning:
        message = warning.message

    return QuestionDeleteResponse(deleted_question_id=question_id, warning=warning, message=message)


@router.get("/questions/{question_id}/stats", response_model=QuestionStatsResponse)
def get_question_stats(question_id: int, db: Session = Depends(get_db)):
    _question_or_404(db, question_id)
    answers = db.query(models.Answer).filter(models.Answer.question_id == question_id).all()
    times_answered = len(answers)
    correct_answers = sum(1 for a in answers if a.is_correct)
    success_rate = (correct_answers / times_answered) if times_answered else 0.0
    return QuestionStatsResponse(
        question_id=question_id,
        times_answered=times_answered,
        correct_answers=correct_answers,
        success_rate=success_rate,
    )


# --- Export / Import ---

@router.get("/content/export", response_model=ContentExport)
def export_content(db: Session = Depends(get_db)):
    themes = db.query(models.Theme).order_by(models.Theme.id).all()
    questions = db.query(models.Question).order_by(models.Question.id).all()
    return ContentExport(themes=themes, questions=questions)


@router.post("/content/import", response_model=ContentImportResponse)
def import_content(payload: ContentImportRequest, db: Session = Depends(get_db)):
    # AD-5 : une seule transaction, un seul commit en fin d'endpoint.
    # Les payloads sont déjà validés par les schémas Pydantic (ThemeCreate/QuestionCreate)
    # avant que ce handler ne s'exécute ; toute entrée invalide échoue en 422 sans rien insérer.
    created_themes = []
    id_remap: dict[int, int] = {}
    for t in payload.themes:
        data = t.model_dump(exclude={"source_id"})
        data["category"] = models.ThemeCategory(data["category"])
        theme = models.Theme(**data)
        db.add(theme)
        _flush_or_400(db)  # attribue l'id sans committer, pour le remappage ci-dessous
        if t.source_id is not None:
            id_remap[t.source_id] = theme.id
        created_themes.append(theme)

    created_questions = []
    for q in payload.questions:
        data = q.model_dump()
        # Remappe vers le thème réimporté dans ce même payload si applicable — sans
        # ce remappage, un export puis réimport rattache la question à l'ancien id
        # de thème, périmé (trouvé en revue de code).
        if data.get("theme_id") in id_remap:
            data["theme_id"] = id_remap[data["theme_id"]]
        elif data.get("theme_id") is not None:
            _theme_exists_or_404(db, data["theme_id"])
        data["wrong_answers"] = json.dumps(data["wrong_answers"])
        data["difficulty"] = models.Difficulty(data["difficulty"])
        created_questions.append(models.Question(**data))
    db.add_all(created_questions)
    _flush_or_400(db)

    for theme in created_themes:
        _log_history(db, "theme", theme.id, "created", f"{theme.name} (import)")
    for question in created_questions:
        _log_history(db, "question", question.id, "created", f"{question.text[:100]} (import)")

    _commit_or_400(db)

    return ContentImportResponse(
        themes_created=len(created_themes),
        questions_created=len(created_questions),
        message=f"{len(created_themes)} thème(s) et {len(created_questions)} question(s) importés.",
    )
