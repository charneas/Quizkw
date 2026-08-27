"""Domaine "account" (Epic O, Story O.2.2) : statistiques personnelles du
Compte connecté. Distinct de main_auth_discord.py (domaine "auth", flux
OAuth login/logout) — DELETE /account (Story O.3.1, RGPD) rejoindra ce même
fichier plus tard."""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.account_manager import resolve_account_id_from_request
from app.account_stats import compute_account_stats
from app.database import get_db
from app.rate_limit import limiter

router = APIRouter(prefix="/account", tags=["Account"])


@router.get("/stats")
@limiter.limit("60/minute")
def account_stats(request: Request, db: Session = Depends(get_db)):
    account_id = resolve_account_id_from_request(request, db)
    if account_id is None:
        raise HTTPException(status_code=401, detail="Non connecté.")
    return compute_account_stats(db, account_id)
