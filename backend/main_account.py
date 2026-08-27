"""Domaine "account" (Epic O, Story O.2.2/O.3.1) : statistiques personnelles
et suppression du Compte connecté. Distinct de main_auth_discord.py (domaine
"auth", flux OAuth login/logout)."""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.account_manager import DISCORD_COOKIE_NAME, resolve_account_from_request, resolve_account_id_from_request
from app.account_stats import compute_account_stats
from app.database import get_db
from app.rate_limit import limiter
from main_auth_discord import DISCORD_SESSION_COOKIE_SECURE

router = APIRouter(prefix="/account", tags=["Account"])


@router.get("/stats")
@limiter.limit("60/minute")
def account_stats(request: Request, db: Session = Depends(get_db)):
    account_id = resolve_account_id_from_request(request, db)
    if account_id is None:
        raise HTTPException(status_code=401, detail="Non connecté.")
    return compute_account_stats(db, account_id)


@router.delete("")
@limiter.limit("10/minute")
def delete_account(request: Request, db: Session = Depends(get_db)):
    """Suppression définitive du Compte (Story O.3.1, FR6/NFR1) : jamais un
    flag de désactivation — la ligne `Account` disparaît immédiatement. Les
    `Player`/`Answer` déjà liés survivent orphelins (`account_id` mis à NULL
    par la contrainte DB `ON DELETE SET NULL` posée en migration, AD-21),
    aucune suppression en cascade ici. Le cookie de session est ensuite effacé
    (même traitement que POST /auth/discord/logout) pour que le joueur soit
    immédiatement ramené à l'état non connecté."""
    account = resolve_account_from_request(request, db)
    if account is None:
        raise HTTPException(status_code=401, detail="Non connecté.")

    db.delete(account)
    db.commit()

    response = JSONResponse({"message": "Compte supprimé."})
    response.delete_cookie(
        key=DISCORD_COOKIE_NAME,
        httponly=True,
        samesite="strict",
        secure=DISCORD_SESSION_COOKIE_SECURE,
    )
    return response
