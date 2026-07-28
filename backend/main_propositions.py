"""
Router de soumission publique de propositions de question (Epic F-ext,
Story F-ext-1.1). Endpoint non authentifié par conception (FR1) : distinct du
routeur admin, qui deviendra authentifié en F-ext-2.1.
"""
import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas

router = APIRouter(prefix="/propositions", tags=["Propositions"])


def _commit_or_400(db: Session) -> None:
    """AD-5 : l'endpoint possède la transaction et roule en arrière sur le chemin d'exception
    (même pattern que `main_admin.py::_commit_or_400`, ex. thème supprimé entre la
    vérification d'existence et le commit)."""
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail="Contrainte violée (référence invalide).") from e


@router.post("", response_model=schemas.Proposition)
def create_proposition(payload: schemas.PropositionCreate, db: Session = Depends(get_db)):
    if payload.theme_id is not None:
        theme = db.query(models.Theme).filter(models.Theme.id == payload.theme_id).first()
        if not theme:
            raise HTTPException(status_code=404, detail="Thème non trouvé")

    proposition = models.Proposition(
        text=payload.text,
        correct_answer=payload.correct_answer,
        wrong_answers=json.dumps(payload.wrong_answers),
        theme_id=payload.theme_id,
        difficulty=models.Difficulty(payload.difficulty.value),
        status=models.PropositionStatus.PENDING,
    )
    db.add(proposition)
    _commit_or_400(db)
    db.refresh(proposition)
    return proposition
