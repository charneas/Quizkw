from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import models


def resolve_or_create_account(db: Session, discord_id: str, pseudo: str, avatar: str | None) -> models.Account:
    """Résolution-ou-création d'un Account par discord_id (AD-19). Pseudo/avatar
    sont écrasés par les valeurs reçues à chaque appel, réutilisation comprise.

    La contrainte unique DB sur discord_id est la sentinelle d'idempotence face
    à deux logins concurrents pour le même compte Discord — jamais un
    check-then-insert nu : sur IntegrityError après un insert perdant la course,
    on relit la ligne posée par l'autre transaction plutôt que de propager
    l'erreur."""
    account = db.query(models.Account).filter(models.Account.discord_id == discord_id).first()
    if account is not None:
        account.pseudo = pseudo
        account.avatar = avatar
        db.commit()
        db.refresh(account)
        return account

    account = models.Account(discord_id=discord_id, pseudo=pseudo, avatar=avatar)
    db.add(account)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        account = db.query(models.Account).filter(models.Account.discord_id == discord_id).first()
        if account is None:
            # L'IntegrityError ne venait pas de la course discord_id documentée
            # ci-dessus (autre contrainte, ou ligne concurrente elle-même
            # annulée depuis) — propager plutôt que de planter sur un accès
            # None (trouvé en revue de code).
            raise
        account.pseudo = pseudo
        account.avatar = avatar
        db.commit()
        db.refresh(account)
        return account

    db.refresh(account)
    return account
