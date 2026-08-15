"""
Router d'administration de contenu (Epic F, story F.1) : CRUD thèmes/questions,
validation de cohérence, export/import, statistiques d'utilisation.

Authentifié depuis la Story F-ext-2.1 (AD-17) : toutes les routes de ce
routeur, y compris celles créées avant cette story, exigent un cookie de
session admin valide via le guard partagé `require_admin_session`. Seules
`POST /admin/login` et `POST /admin/logout` restent accessibles sans session
(il faut pouvoir se connecter avant d'avoir un cookie).
"""
import json
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import case, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import hash_password, require_admin_session, sign_session, verify_password, COOKIE_NAME, SESSION_COOKIE_SECURE
from app.database import get_db
from app import models, schemas
from app.rate_limit import limiter
from app.schemas_admin import (
    ThemeUpdate, QuestionUpdate,
    ThemeDeleteWarning, ThemeDeleteResponse, QuestionDeleteResponse,
    ContentExport, ContentImportRequest, ContentImportResponse,
    QuestionStatsResponse, QuestionStatsListItem, ThemeStatsResponse,
    MIN_QUESTIONS_PER_THEME, DIFFICULTY_POINTS,
)

router = APIRouter(prefix="/admin", tags=["Admin"], dependencies=[Depends(require_admin_session)])

# Routeur séparé pour login/logout : ces deux routes ne doivent PAS passer par
# le guard `require_admin_session` (on ne peut pas exiger une session pour
# l'obtenir). Même préfixe `/admin`, monté séparément dans main.py.
auth_router = APIRouter(prefix="/admin", tags=["Admin"])


@auth_router.post("/login")
@limiter.limit("10/minute")
def login(request: Request, payload: schemas.AdminLoginRequest, response: Response, db: Session = Depends(get_db)):
    admin = db.query(models.Admin).filter(models.Admin.email == payload.email).first()
    # AC #4 : message générique identique, que l'email soit inconnu ou le mot
    # de passe incorrect — ne jamais révéler si le compte existe (AD-6/NFR1).
    if not admin or not verify_password(payload.password, admin.hashed_password):
        raise HTTPException(status_code=400, detail="Email ou mot de passe incorrect.")
    token = sign_session(admin.id)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="strict",
        secure=SESSION_COOKIE_SECURE,
    )
    return {"message": "Connexion réussie."}


@auth_router.post("/logout")
def logout(response: Response):
    # Mêmes attributs qu'au set_cookie : certains navigateurs n'effacent pas
    # un cookie si samesite/secure ne correspondent pas à ceux posés à l'origine.
    response.delete_cookie(key=COOKIE_NAME, httponly=True, samesite="strict", secure=SESSION_COOKIE_SECURE)
    return {"message": "Déconnexion réussie."}


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


def _proposition_or_404(db: Session, proposition_id: int, for_update: bool = False) -> models.Proposition:
    query = db.query(models.Proposition).filter(models.Proposition.id == proposition_id)
    if for_update:
        # Ferme la fenêtre check-then-act entre la lecture du statut et l'écriture
        # (deux accept concurrents ne doivent pas créer deux Question) — même
        # pattern que _suggestion_or_404(for_update=True) dans main_content_gen.py.
        query = query.with_for_update()
    proposition = query.first()
    if not proposition:
        raise HTTPException(status_code=404, detail="Proposition non trouvée")
    return proposition


def _resolve_or_create_theme(db: Session, new_theme: schemas.ThemeCreate) -> models.Theme:
    """Story F-ext-2.3 (AC #4) : normalise casse/espaces avant comparaison pour
    réutiliser un thème quasi-identique existant plutôt que d'en créer un doublon.
    Spécifique à ce flux d'édition — ne modifie pas POST /admin/themes."""
    normalized = new_theme.name.strip().lower()
    for theme in db.query(models.Theme).all():
        if theme.name.strip().lower() == normalized:
            return theme

    data = new_theme.model_dump()
    data["category"] = models.ThemeCategory(data["category"])
    theme = models.Theme(**data)
    db.add(theme)
    _flush_or_400(db)
    _log_history(db, "theme", theme.id, "created", theme.name)
    return theme


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


@router.get("/stats/questions", response_model=List[QuestionStatsListItem])
def get_all_question_stats(db: Session = Depends(get_db)):
    """Stats agrégées de toutes les questions en une requête (évite le
    N+1 côté front d'un appel par question, story sidebar admin 2026-08-12)."""
    rows = (
        db.query(
            models.Question.id,
            models.Question.text,
            models.Question.theme_id,
            models.Theme.name.label("theme_name"),
            func.count(models.Answer.id).label("times_answered"),
            func.sum(case((models.Answer.is_correct.is_(True), 1), else_=0)).label("correct_answers"),
        )
        .outerjoin(models.Answer, models.Answer.question_id == models.Question.id)
        .outerjoin(models.Theme, models.Theme.id == models.Question.theme_id)
        .group_by(models.Question.id)
        .all()
    )
    return [
        QuestionStatsListItem(
            question_id=r.id,
            text=r.text,
            theme_id=r.theme_id,
            theme_name=r.theme_name,
            times_answered=r.times_answered or 0,
            correct_answers=int(r.correct_answers or 0),
            success_rate=(int(r.correct_answers or 0) / r.times_answered) if r.times_answered else 0.0,
        )
        for r in rows
    ]


@router.get("/stats/themes", response_model=List[ThemeStatsResponse])
def get_theme_stats(db: Session = Depends(get_db)):
    """Stats agrégées par thème (nombre de questions, réponses, taux de
    réussite) — vue d'ensemble complémentaire à /stats/questions."""
    rows = (
        db.query(
            models.Theme.id,
            models.Theme.name,
            func.count(func.distinct(models.Question.id)).label("questions_count"),
            func.count(models.Answer.id).label("times_answered"),
            func.sum(case((models.Answer.is_correct.is_(True), 1), else_=0)).label("correct_answers"),
        )
        .outerjoin(models.Question, models.Question.theme_id == models.Theme.id)
        .outerjoin(models.Answer, models.Answer.question_id == models.Question.id)
        .group_by(models.Theme.id)
        .order_by(models.Theme.name)
        .all()
    )
    return [
        ThemeStatsResponse(
            theme_id=r.id,
            theme_name=r.name,
            questions_count=r.questions_count or 0,
            times_answered=r.times_answered or 0,
            correct_answers=int(r.correct_answers or 0),
            success_rate=(int(r.correct_answers or 0) / r.times_answered) if r.times_answered else 0.0,
        )
        for r in rows
    ]


# --- Propositions (Epic F-ext-2, modération) ---

@router.get("/propositions/pending", response_model=list[schemas.Proposition])
def list_pending_propositions(db: Session = Depends(get_db)):
    return (
        db.query(models.Proposition)
        .filter(models.Proposition.status == models.PropositionStatus.PENDING)
        .order_by(models.Proposition.id)
        .all()
    )


@router.put("/propositions/{proposition_id}", response_model=schemas.Proposition)
def update_proposition(proposition_id: int, payload: schemas.PropositionUpdate, db: Session = Depends(get_db)):
    proposition = _proposition_or_404(db, proposition_id)

    # AC #8 : éditer une proposition déjà tranchée réécrirait silencieusement
    # l'historique de décision (risque nommé par AD-18) — refusé explicitement.
    if proposition.status != models.PropositionStatus.PENDING:
        raise HTTPException(
            status_code=400,
            detail="Seule une proposition en attente peut être éditée.",
        )

    updates = payload.model_dump(exclude_unset=True, exclude={"new_theme"})

    # Basé sur la présence de la clé dans la requête (exclude_unset), pas sur
    # payload.theme_id is not None : un theme_id explicitement null envoyé avec
    # new_theme contournerait sinon cette vérification (theme_id=None ne
    # déclenche pas "is not None" mais reste une valeur explicitement fournie).
    if "theme_id" in updates and payload.new_theme is not None:
        raise HTTPException(
            status_code=400,
            detail="Fournir soit theme_id, soit new_theme, pas les deux.",
        )

    if "theme_id" in updates and updates["theme_id"] is not None:
        _theme_exists_or_404(db, updates["theme_id"])

    if payload.new_theme is not None:
        theme = _resolve_or_create_theme(db, payload.new_theme)
        updates["theme_id"] = theme.id

    if "wrong_answers" in updates and updates["wrong_answers"] is not None:
        updates["wrong_answers"] = json.dumps(updates["wrong_answers"])

    if "difficulty" in updates and updates["difficulty"] is not None:
        updates["difficulty"] = models.Difficulty(updates["difficulty"])

    for field, value in updates.items():
        setattr(proposition, field, value)

    _log_history(db, "proposition", proposition.id, "updated", ", ".join(updates.keys()) or "aucun champ")
    _commit_or_400(db)
    db.refresh(proposition)
    return proposition


@router.post("/propositions/{proposition_id}/accept", response_model=schemas.AcceptPropositionResponse)
def accept_proposition(proposition_id: int, db: Session = Depends(get_db)):
    proposition = _proposition_or_404(db, proposition_id, for_update=True)

    if proposition.status != models.PropositionStatus.PENDING:
        raise HTTPException(
            status_code=400,
            detail=f"Proposition déjà traitée (statut : {proposition.status.value}).",
        )

    if proposition.theme_id is None:
        raise HTTPException(
            status_code=400,
            detail="Le thème doit être résolu avant acceptation (proposition encore « À déterminer »).",
        )

    theme = _theme_or_404(db, proposition.theme_id)

    question = models.Question(
        text=proposition.text,
        category=theme.name,
        difficulty=proposition.difficulty,
        points=DIFFICULTY_POINTS[proposition.difficulty.value],
        correct_answer=proposition.correct_answer,
        wrong_answers=proposition.wrong_answers,
        theme_id=proposition.theme_id,
        question_number=None,
        image_url=proposition.image_url,
    )
    db.add(question)
    _flush_or_400(db)

    proposition.status = models.PropositionStatus.ACCEPTED

    _log_history(db, "proposition", proposition.id, "accepted", f"question_id={question.id}")
    _log_history(db, "question", question.id, "created", f"{question.text[:100]} (via proposition {proposition.id})")

    _commit_or_400(db)

    return schemas.AcceptPropositionResponse(
        proposition_id=proposition.id,
        question_id=question.id,
        message=f"Proposition acceptée : question créée sous le thème '{theme.name}'.",
    )


@router.post("/propositions/{proposition_id}/reject", response_model=schemas.Proposition)
def reject_proposition(proposition_id: int, payload: schemas.RejectPropositionRequest, db: Session = Depends(get_db)):
    proposition = _proposition_or_404(db, proposition_id, for_update=True)

    if proposition.status != models.PropositionStatus.PENDING:
        raise HTTPException(
            status_code=400,
            detail=f"Proposition déjà traitée (statut : {proposition.status.value}).",
        )

    proposition.status = models.PropositionStatus.REJECTED
    proposition.rejection_reason = payload.reason

    _log_history(db, "proposition", proposition.id, "rejected", payload.reason[:100])

    _commit_or_400(db)
    db.refresh(proposition)
    return proposition


@router.get("/propositions/rejected", response_model=list[schemas.Proposition])
def list_rejected_propositions(db: Session = Depends(get_db)):
    return (
        db.query(models.Proposition)
        .filter(models.Proposition.status == models.PropositionStatus.REJECTED)
        .order_by(models.Proposition.id)
        .all()
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
