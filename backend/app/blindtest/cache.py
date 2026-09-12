"""Cache de matching entre imports (Story 1.3).

Une résolution réussie (`youtube_video_id`) est mémorisée dans `MatchCache`
pour ne jamais re-solliciter `idonthavespotify`/`search.list` sur un morceau
déjà connu, quel que soit l'import qui l'a d'abord résolu (FR3).

Clé de cache : ISRC en priorité, sinon `(title, artist)` normalisé. La
normalisation (minuscule, accents/ponctuation retirés, mentions "feat."/"ft."
supprimées) vit ICI uniquement, et est utilisée à la fois en lecture
(`lookup`) et en écriture (`store`) pour que les clés ne divergent jamais.

Seuls `matching.py` et `main_blindtest.py` (import direct YouTube) écrivent
dans `MatchCache` — le reste du code (Epic 2 notamment) n'y accède jamais.
"""
import re
import unicodedata
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.blindtest.models import MatchCache

_FEAT_RE = re.compile(r"\b(feat|ft)\b\.?.*$", re.IGNORECASE)
_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
_WS_RE = re.compile(r"\s+")


def _strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _normalize_part(value: str) -> str:
    value = value.lower()
    value = _strip_accents(value)
    value = _FEAT_RE.sub("", value)
    value = _PUNCT_RE.sub(" ", value)
    value = _WS_RE.sub(" ", value).strip()
    return value


def normalize_key(title: str, artist: str) -> str:
    """Clé de cache normalisée pour `(title, artist)` : minuscule, accents et
    ponctuation retirés, mentions "feat."/"ft." supprimées. Utilisée à la
    fois par `lookup` et `store` pour garantir des clés cohérentes."""
    return f"{_normalize_part(title or '')}|{_normalize_part(artist or '')}"


def lookup(db: Session, isrc: Optional[str], title: str, artist: str) -> Optional[str]:
    """Cherche une résolution déjà connue : par ISRC en priorité, sinon par
    `(title, artist)` normalisé. Renvoie `None` si aucun des deux ne
    correspond (ou si `isrc` est vide/None, auquel cas seule la clé
    normalisée est consultée)."""
    if isrc:
        row = db.query(MatchCache).filter(MatchCache.isrc == isrc).first()
        if row:
            return row.youtube_video_id

    key = normalize_key(title, artist)
    row = db.query(MatchCache).filter(MatchCache.normalized_key == key).first()
    if row:
        return row.youtube_video_id

    return None


def store(
    db: Session,
    isrc: Optional[str],
    title: str,
    artist: str,
    youtube_video_id: str,
    overwrite: bool = False,
) -> None:
    """Enregistre une résolution réussie. Upsert-safe : si une ligne
    correspondant déjà à l'ISRC ou à la clé normalisée existe, ne réécrit
    rien par défaut (pas de retry/invalidation pour le matching auto,
    tolérant aux races).

    `overwrite=True` (utilisé par la correction admin `resolve_track`, cf.
    `main_blindtest.py`) fait au contraire écraser `youtube_video_id` sur la
    ligne existante — c'est tout le but de cette correction : remplacer un
    mauvais match mémorisé par le bon, pas laisser une ligne périmée pointer
    vers l'ancienne vidéo.

    Ne commit pas : c'est aux appelants de commiter (`matching.py` commit
    juste après son appel à `store`, `main_blindtest.py` commit une seule
    fois à la fin de sa boucle d'import / après sa correction admin). Ça
    préserve l'invariant "pas d'écriture partielle" de `import_playlist` —
    un `db.commit()` ici clôturerait et rouvrirait la transaction,
    persistant durablement les lignes déjà ajoutées même si le reste de la
    requête échoue ensuite.

    L'existence-check-puis-insert n'est pas atomique : deux résolutions
    concurrentes du même morceau peuvent toutes deux passer le check avant
    qu'aucune n'ait flush/commit, puis entrer en conflit sur la contrainte
    unique (isrc/normalized_key). C'est traité comme un no-op (l'autre
    writer a gagné la course, ce qui est le résultat voulu) en absorbant
    l'`IntegrityError` au flush et en faisant un rollback."""
    if not youtube_video_id:
        return

    if isrc:
        existing = db.query(MatchCache).filter(MatchCache.isrc == isrc).first()
        if existing:
            if overwrite:
                existing.youtube_video_id = youtube_video_id
                db.flush()
            return
        _insert_safely(db, MatchCache(isrc=isrc, normalized_key=None, youtube_video_id=youtube_video_id))
        return

    key = normalize_key(title, artist)
    existing = db.query(MatchCache).filter(MatchCache.normalized_key == key).first()
    if existing:
        if overwrite:
            existing.youtube_video_id = youtube_video_id
            db.flush()
        return
    _insert_safely(db, MatchCache(isrc=None, normalized_key=key, youtube_video_id=youtube_video_id))


def _insert_safely(db: Session, row: MatchCache) -> None:
    """Insère `row` sous un savepoint (`begin_nested`) pour qu'un conflit de
    contrainte unique (race entre deux résolutions concurrentes du même
    morceau) ne fasse rollback que de cet insert — jamais du reste de la
    session (les `Playlist`/`Track` en attente dans la boucle appelante de
    `import_playlist` doivent rester intacts)."""
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError:
        pass
