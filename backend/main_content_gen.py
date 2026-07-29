"""
Router de génération semi-automatique de contenu (Epic F, story F.2) :
pipeline Wikipedia -> Claude -> suggestion en attente -> validation humaine,
mix de catégories, signalement joueur (résolution admin), historique.

Authentifié depuis la Story F-ext-2.1 (AD-17) : ce routeur est monté sous
`/admin/content`, donc couvert par le guard partagé `require_admin_session`
comme toute route `/admin/*` (AD-17 : "every route under /admin"). Seul
`player_router` (signalement joueur, hors préfixe /admin) reste public.
"""
import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import require_admin_session
from app.database import get_db
from app import models
from app.wikipedia_client import get_wikipedia_extract
from app.content_generator import generate_content
from app.schemas_admin import DIFFICULTY_POINTS  # AD-13 : même mapping que F.1, pas de redéfinition
from app.schemas_content_gen import (
    GenerateContentRequest, ContentSuggestionResponse, GeneratedQuestion,
    ApproveSuggestionResponse, RejectSuggestionRequest, RejectSuggestionResponse,
    CategoryMixResponse, CategoryMixEntry, TARGET_CATEGORY_MIX,
    FlagQuestionRequest, FlagQuestionResponse,
    ContentFlagResponse, ResolveFlagRequest,
    ContentHistoryEntry,
)

router = APIRouter(prefix="/admin/content", tags=["Content Generation"], dependencies=[Depends(require_admin_session)])
# Route joueur (signalement), volontairement HORS préfixe /admin (AD-12 : route
# joueur ordinaire, publique comme le reste de l'API — pas une capacité admin).
player_router = APIRouter(tags=["Content Flagging"])


def _commit_or_400(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail="Contrainte violée.") from e


def _flush_or_400(db: Session) -> None:
    """Un flush intermédiaire (avant de logger un ContentHistory qui a besoin de
    l'id auto-généré) doit aussi traduire une IntegrityError en 400, pas la
    laisser fuiter en 500 (même garde que main_admin._flush_or_400)."""
    try:
        db.flush()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail="Contrainte violée.") from e


def _log_history(db: Session, entity_type: str, entity_id: int, action: str, detail: str | None = None) -> None:
    db.add(models.ContentHistory(entity_type=entity_type, entity_id=entity_id, action=action, detail=detail))


def _mix_snapshot(db: Session) -> CategoryMixResponse:
    themes = db.query(models.Theme).all()
    total = len(themes)
    counts = {cat: 0 for cat in models.ThemeCategory}
    for theme in themes:
        counts[theme.category] += 1

    mix = []
    biggest_gap_category = None
    biggest_gap = -1.0
    for cat, target in TARGET_CATEGORY_MIX.items():
        model_cat = models.ThemeCategory(cat.value)
        count = counts[model_cat]
        current_ratio = (count / total) if total else 0.0
        gap = target - current_ratio
        if gap > biggest_gap:
            biggest_gap = gap
            biggest_gap_category = cat
        mix.append(CategoryMixEntry(category=cat, current_count=count, current_ratio=current_ratio, target_ratio=target))

    return CategoryMixResponse(total_themes=total, mix=mix, recommended_category=biggest_gap_category)


# --- Génération ---

@router.get("/category-mix", response_model=CategoryMixResponse)
def get_category_mix(db: Session = Depends(get_db)):
    return _mix_snapshot(db)


@router.post("/generate", response_model=ContentSuggestionResponse)
def generate_suggestion(request: GenerateContentRequest, db: Session = Depends(get_db)):
    try:
        extract = get_wikipedia_extract(request.topic)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        # Échec réseau/HTTP Wikipedia (pas "sujet introuvable") : fournisseur
        # externe en échec, pas une 404 métier (AD-6).
        raise HTTPException(status_code=502, detail=str(e))

    category = request.category
    if category is None:
        category = _mix_snapshot(db).recommended_category

    try:
        generated = generate_content(request.topic, extract, category)
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=502, detail=f"Échec de la génération de contenu : {e}")

    suggestion = models.ContentSuggestion(
        topic=request.topic,
        wikipedia_extract=extract,
        generated_theme_name=generated.theme_name,
        generated_category=models.ThemeCategory(generated.category.value),
        generated_questions=[q.model_dump() for q in generated.questions],
        status=models.SuggestionStatus.PENDING,
    )
    db.add(suggestion)
    _flush_or_400(db)
    _log_history(db, "suggestion", suggestion.id, "generated", f"topic={request.topic}")
    _commit_or_400(db)
    db.refresh(suggestion)
    return suggestion


@router.get("/suggestions", response_model=list[ContentSuggestionResponse])
def list_suggestions(status: str | None = None, db: Session = Depends(get_db)):
    query = db.query(models.ContentSuggestion)
    if status is not None:
        try:
            status_enum = models.SuggestionStatus(status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Statut invalide : {status}")
        query = query.filter(models.ContentSuggestion.status == status_enum)
    return query.order_by(models.ContentSuggestion.created_at.desc()).all()


def _suggestion_or_404(db: Session, suggestion_id: int, for_update: bool = False) -> models.ContentSuggestion:
    query = db.query(models.ContentSuggestion).filter(models.ContentSuggestion.id == suggestion_id)
    if for_update:
        # Verrou de ligne : ferme la fenêtre check-then-act entre la lecture du
        # statut et l'écriture (deux approve concurrents créeraient sinon les
        # questions en double avant que le second échoue sur le thème — trouvé
        # en revue de code). No-op inoffensif sous SQLite (verrouillage fichier
        # entier natif), réellement effectif sous PostgreSQL (cible AD-14).
        query = query.with_for_update()
    suggestion = query.first()
    if not suggestion:
        raise HTTPException(status_code=404, detail="Suggestion non trouvée")
    return suggestion


@router.post("/suggestions/{suggestion_id}/approve", response_model=ApproveSuggestionResponse)
def approve_suggestion(suggestion_id: int, db: Session = Depends(get_db)):
    suggestion = _suggestion_or_404(db, suggestion_id, for_update=True)
    if suggestion.status != models.SuggestionStatus.PENDING:
        raise HTTPException(status_code=400, detail=f"Suggestion déjà traitée (statut : {suggestion.status.value})")

    # Réutilise la même logique de création que F.1 (main_admin.create_theme /
    # create_question) plutôt que d'en dupliquer une variante (AD-13).
    theme = db.query(models.Theme).filter(models.Theme.name == suggestion.generated_theme_name).first()
    theme_reused = theme is not None
    if theme is None:
        theme = models.Theme(
            name=suggestion.generated_theme_name,
            category=suggestion.generated_category,
            difficulty_level=5,
            description=f"Généré automatiquement à partir du sujet Wikipedia « {suggestion.topic} ».",
        )
        db.add(theme)
        _flush_or_400(db)

    # Trié par difficulté croissante puis numéroté 1..N : la Manche 2 attend
    # une progression easy -> medium -> hard via question_number (comme
    # seed.py le fait à la main) — jusqu'ici jamais renseigné ici, ce qui
    # rendait les questions générées inutilisables pour cette progression
    # (bug trouvé en revue).
    DIFFICULTY_ORDER = {"easy": 0, "medium": 1, "hard": 2}
    sorted_raw = sorted(
        suggestion.generated_questions,
        key=lambda raw: DIFFICULTY_ORDER.get(raw.get("difficulty"), 1),
    )

    created_count = 0
    created_questions = []
    for i, raw in enumerate(sorted_raw, start=1):
        # Revalidé au lieu d'un accès dict en confiance : la suggestion peut avoir
        # été écrite par une version antérieure du contrat GeneratedQuestion
        # (trouvé en revue de code — le JSON n'est validé qu'à la génération,
        # jamais relu ici avant cette correction).
        q = GeneratedQuestion.model_validate(raw)
        question = models.Question(
            text=q.text,
            category=suggestion.generated_theme_name,
            difficulty=models.Difficulty(q.difficulty.value),
            points=DIFFICULTY_POINTS[q.difficulty.value],
            correct_answer=q.correct_answer,
            wrong_answers=json.dumps(q.wrong_answers),
            theme_id=theme.id,
            question_number=i,
        )
        db.add(question)
        created_questions.append(question)
        created_count += 1
    _flush_or_400(db)

    suggestion.status = models.SuggestionStatus.APPROVED
    from datetime import datetime, timezone
    suggestion.reviewed_at = datetime.now(timezone.utc)
    suggestion.created_theme_id = theme.id

    _log_history(db, "suggestion", suggestion.id, "approved", f"theme_id={theme.id}, questions={created_count}")
    if not theme_reused:
        _log_history(db, "theme", theme.id, "created", f"via suggestion {suggestion.id}")
    for question in created_questions:
        _log_history(db, "question", question.id, "created", f"{question.text[:100]} (via suggestion {suggestion.id})")

    _commit_or_400(db)

    return ApproveSuggestionResponse(
        suggestion_id=suggestion.id,
        theme_id=theme.id,
        questions_created=created_count,
        message=f"{created_count} question(s) créée(s) sous le thème '{theme.name}'.",
    )


@router.post("/suggestions/{suggestion_id}/reject", response_model=RejectSuggestionResponse)
def reject_suggestion(suggestion_id: int, request: RejectSuggestionRequest, db: Session = Depends(get_db)):
    suggestion = _suggestion_or_404(db, suggestion_id, for_update=True)
    if suggestion.status != models.SuggestionStatus.PENDING:
        raise HTTPException(status_code=400, detail=f"Suggestion déjà traitée (statut : {suggestion.status.value})")

    from datetime import datetime, timezone
    suggestion.status = models.SuggestionStatus.REJECTED
    suggestion.reviewed_at = datetime.now(timezone.utc)
    suggestion.rejection_reason = request.reason

    _log_history(db, "suggestion", suggestion.id, "rejected", request.reason)
    _commit_or_400(db)

    return RejectSuggestionResponse(suggestion_id=suggestion.id, message="Suggestion rejetée.")


# --- Signalements (résolution admin) ---

@router.get("/flags", response_model=list[ContentFlagResponse])
def list_flags(resolved: bool | None = None, db: Session = Depends(get_db)):
    query = db.query(models.ContentFlag)
    if resolved is not None:
        query = query.filter(models.ContentFlag.resolved == resolved)
    return query.order_by(models.ContentFlag.flagged_at.desc()).all()


@router.post("/flags/{flag_id}/resolve", response_model=ContentFlagResponse)
def resolve_flag(flag_id: int, request: ResolveFlagRequest, db: Session = Depends(get_db)):
    flag = db.query(models.ContentFlag).filter(models.ContentFlag.id == flag_id).first()
    if not flag:
        raise HTTPException(status_code=404, detail="Signalement non trouvé")

    from datetime import datetime, timezone
    flag.resolved = True
    flag.resolved_at = datetime.now(timezone.utc)
    flag.resolution_note = request.note

    _log_history(db, "flag", flag.id, "resolved", request.note)
    _commit_or_400(db)
    db.refresh(flag)
    return flag


# --- Historique ---

@router.get("/history", response_model=list[ContentHistoryEntry])
def get_history(entity_type: str | None = None, entity_id: int | None = None, limit: int = 100, db: Session = Depends(get_db)):
    query = db.query(models.ContentHistory)
    if entity_type is not None:
        query = query.filter(models.ContentHistory.entity_type == entity_type)
    if entity_id is not None:
        query = query.filter(models.ContentHistory.entity_id == entity_id)
    return query.order_by(models.ContentHistory.created_at.desc()).limit(limit).all()


# --- Signalement joueur (route publique, hors /admin) ---

@player_router.post("/questions/{question_id}/flag", response_model=FlagQuestionResponse)
def flag_question(question_id: int, request: FlagQuestionRequest, db: Session = Depends(get_db)):
    question = db.query(models.Question).filter(models.Question.id == question_id).first()
    if not question:
        raise HTTPException(status_code=404, detail="Question non trouvée")

    flag = models.ContentFlag(question_id=question_id, reason=request.reason)
    db.add(flag)
    _flush_or_400(db)
    _log_history(db, "flag", flag.id, "flagged", f"question_id={question_id}")
    _commit_or_400(db)

    return FlagQuestionResponse(flag_id=flag.id, question_id=question_id, message="Signalement enregistré, merci.")
