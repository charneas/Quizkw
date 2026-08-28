"""Agrégation des statistiques personnelles par thème (Epic O, Story O.2.2,
AD-20). Calcul à la lecture, jamais de compteur maintenu — un agrégat frais à
chaque ouverture de l'overlay Profil, combinant deux mécaniques de jeu :

- Manche 1 (`Answer`) : réponse d'équipe, attribuée à chaque `Player` de
  l'équipe au moment de la réponse (`Answer.team_id -> Team -> Player.team_id`)
  — décision utilisateur explicite (voir Dev Notes de la story), pas une
  notion de "qui a tapé la réponse", qui n'existe pas dans le jeu.
- Round 2 (`PlayerRound2Stats`) : déjà individuel par construction.

Les deux sources ont des formes différentes (lignes individuelles à agréger
vs compteurs déjà agrégés par thème/partie) — fusionnées en Python plutôt que
par un UNION SQL, plus simple à écrire correctement.
"""
from sqlalchemy.orm import Session

from . import models

MIN_ANSWERS_FOR_PERSONAL_STAT = 10  # FR4


def _merge_totals(*sources: dict[int, dict[str, int]]) -> dict[int, dict[str, int]]:
    merged: dict[int, dict[str, int]] = {}
    for source in sources:
        for theme_id, counts in source.items():
            bucket = merged.setdefault(theme_id, {"correct": 0, "total": 0})
            bucket["correct"] += counts["correct"]
            bucket["total"] += counts["total"]
    return merged


def _manche1_theme_totals(db: Session, account_id: int | None) -> dict[int, dict[str, int]]:
    """Personnel (account_id fourni) : filtre sur les équipes où ce compte a
    au moins un joueur, via une sous-requête sur team_id distincts — jamais
    une jointure Player directe sur la requête Answer/Question, qui
    dupliquerait chaque Answer autant de fois que ce compte a de joueurs sur
    cette équipe (ex. deux pseudos rejoints par erreur, revue de code). Global
    (account_id=None) : jamais de jointure Player du tout."""
    query = db.query(models.Question.theme_id, models.Answer.is_correct).join(
        models.Answer, models.Answer.question_id == models.Question.id
    )
    if account_id is not None:
        team_ids = db.query(models.Player.team_id).filter(
            models.Player.account_id == account_id,
            models.Player.team_id.isnot(None),
        ).distinct()
        query = query.filter(models.Answer.team_id.in_(team_ids))

    totals: dict[int, dict[str, int]] = {}
    for theme_id, is_correct in query.all():
        # Revue de code : les questions sans thème (`theme_id is None`, valide
        # en base) étaient auparavant exclues entièrement — y compris de la
        # stat générale (FR5, censée couvrir "toutes questions confondues"
        # sans notion de thème). Regroupées ici sous la clé `None`, exclue
        # explicitement de la liste par thème dans compute_account_stats
        # (aucun `Theme` ne peut avoir cet id) mais comptée dans le général.
        bucket = totals.setdefault(theme_id, {"correct": 0, "total": 0})
        bucket["total"] += 1
        if is_correct:
            bucket["correct"] += 1
    return totals


def _round2_theme_totals(db: Session, account_id: int | None) -> dict[int, dict[str, int]]:
    query = db.query(
        models.PlayerRound2Stats.theme_id,
        models.PlayerRound2Stats.correct_answers,
        models.PlayerRound2Stats.questions_answered,
    )
    if account_id is not None:
        query = query.join(
            models.Player, models.Player.id == models.PlayerRound2Stats.player_id
        ).filter(models.Player.account_id == account_id)

    totals: dict[int, dict[str, int]] = {}
    for theme_id, correct, answered in query.all():
        # Même raison que _manche1_theme_totals : ne pas exclure les lignes
        # sans thème de la stat générale.
        bucket = totals.setdefault(theme_id, {"correct": 0, "total": 0})
        bucket["correct"] += correct or 0
        bucket["total"] += answered or 0
    return totals


def _theme_totals(db: Session, account_id: int | None) -> dict[int, dict[str, int]]:
    return _merge_totals(
        _manche1_theme_totals(db, account_id),
        _round2_theme_totals(db, account_id),
    )


def compute_account_stats(db: Session, account_id: int) -> dict:
    """Renvoie l'agrégat complet pour l'overlay Profil : stat générale
    (ungated, FR5) et stats par thème (gated à MIN_ANSWERS_FOR_PERSONAL_STAT
    réponses personnelles, FR4), personnel et global côte à côte."""
    personal = _theme_totals(db, account_id)
    global_ = _theme_totals(db, None)

    # Seuls les thèmes où ce compte a au moins une réponse personnelle sont
    # renvoyés — un thème jamais joué par ce compte n'a pas sa place dans son
    # Profil, même s'il existe globalement (trouvé lors de l'écriture des
    # tests : la version initiale renvoyait l'union avec le global, listant
    # des thèmes que le compte n'a jamais touchés).
    theme_ids = {
        theme_id for theme_id, counts in personal.items()
        if theme_id is not None and counts["total"] > 0
    }
    theme_names = {}
    if theme_ids:
        for theme_id, name in db.query(models.Theme.id, models.Theme.name).filter(
            models.Theme.id.in_(theme_ids)
        ).all():
            theme_names[theme_id] = name

    themes = []
    for theme_id in sorted(theme_ids):
        p = personal.get(theme_id, {"correct": 0, "total": 0})
        g = global_.get(theme_id, {"correct": 0, "total": 0})
        themes.append({
            "theme_id": theme_id,
            "theme_name": theme_names.get(theme_id, ""),
            "personal_correct": p["correct"],
            "personal_total": p["total"],
            "global_correct": g["correct"],
            "global_total": g["total"],
            "insufficient_data": p["total"] < MIN_ANSWERS_FOR_PERSONAL_STAT,
        })

    personal_general_correct = sum(v["correct"] for v in personal.values())
    personal_general_total = sum(v["total"] for v in personal.values())
    global_general_correct = sum(v["correct"] for v in global_.values())
    global_general_total = sum(v["total"] for v in global_.values())

    return {
        "general": {
            "personal_correct": personal_general_correct,
            "personal_total": personal_general_total,
            "global_correct": global_general_correct,
            "global_total": global_general_total,
        },
        "themes": themes,
    }
