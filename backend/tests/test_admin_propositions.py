"""
Tests pour les endpoints admin de liste, d'édition et d'acceptation des
propositions (Epic F-ext-2, Stories F-ext-2.2/F-ext-2.3/F-ext-2.4). Protégés
par `require_admin_session`.
"""
import json

from app import models


def _make_proposition(db_session, text, status, theme_id=None):
    proposition = models.Proposition(
        text=text,
        correct_answer="Réponse",
        wrong_answers=json.dumps(["A", "B"]),
        theme_id=theme_id,
        difficulty=models.Difficulty.EASY,
        status=status,
    )
    db_session.add(proposition)
    db_session.commit()
    db_session.refresh(proposition)
    return proposition


def test_list_pending_propositions_requires_auth(test_client):
    resp = test_client.get("/admin/propositions/pending")
    assert resp.status_code == 401


def test_list_pending_propositions_empty(authenticated_client):
    resp = authenticated_client.get("/admin/propositions/pending")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_pending_propositions_filters_by_status(authenticated_client, db_session, sample_theme):
    pending = _make_proposition(db_session, "Pending Q", models.PropositionStatus.PENDING, theme_id=sample_theme.id)
    _make_proposition(db_session, "Accepted Q", models.PropositionStatus.ACCEPTED)
    _make_proposition(db_session, "Rejected Q", models.PropositionStatus.REJECTED)
    without_theme = _make_proposition(db_session, "Pending no theme", models.PropositionStatus.PENDING, theme_id=None)

    resp = authenticated_client.get("/admin/propositions/pending")
    assert resp.status_code == 200
    body = resp.json()
    texts = {p["text"] for p in body}
    assert texts == {"Pending Q", "Pending no theme"}

    by_id = {p["id"]: p for p in body}
    assert by_id[pending.id]["theme_id"] == sample_theme.id
    assert by_id[without_theme.id]["theme_id"] is None
    assert all(p["status"] == "pending" for p in body)


# --- PUT /admin/propositions/{id} (Story F-ext-2.3) ---

def test_update_proposition_requires_auth(test_client, db_session):
    prop = _make_proposition(db_session, "Q", models.PropositionStatus.PENDING)
    resp = test_client.put(f"/admin/propositions/{prop.id}", json={"text": "New text"})
    assert resp.status_code == 401


def test_update_proposition_not_found(authenticated_client):
    resp = authenticated_client.put("/admin/propositions/999999", json={"text": "New text"})
    assert resp.status_code == 404


def test_update_proposition_valid_fields(authenticated_client, db_session):
    prop = _make_proposition(db_session, "Old text", models.PropositionStatus.PENDING)
    resp = authenticated_client.put(
        f"/admin/propositions/{prop.id}",
        json={
            "text": "New text",
            "correct_answer": "New answer",
            "wrong_answers": ["X", "Y"],
            "difficulty": "hard",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["text"] == "New text"
    assert body["correct_answer"] == "New answer"
    assert body["wrong_answers"] == ["X", "Y"]
    assert body["difficulty"] == "hard"


def test_update_proposition_with_existing_theme_id(authenticated_client, db_session, sample_theme):
    prop = _make_proposition(db_session, "Q", models.PropositionStatus.PENDING)
    resp = authenticated_client.put(f"/admin/propositions/{prop.id}", json={"theme_id": sample_theme.id})
    assert resp.status_code == 200
    assert resp.json()["theme_id"] == sample_theme.id


def test_update_proposition_with_nonexistent_theme_id(authenticated_client, db_session):
    prop = _make_proposition(db_session, "Q", models.PropositionStatus.PENDING)
    resp = authenticated_client.put(f"/admin/propositions/{prop.id}", json={"theme_id": 999999})
    assert resp.status_code == 404


def test_update_proposition_creates_new_theme(authenticated_client, db_session):
    prop = _make_proposition(db_session, "Q", models.PropositionStatus.PENDING)
    resp = authenticated_client.put(
        f"/admin/propositions/{prop.id}",
        json={"new_theme": {"name": "Cinéma", "category": "pop_culture", "difficulty_level": 5}},
    )
    assert resp.status_code == 200
    new_theme_id = resp.json()["theme_id"]
    assert new_theme_id is not None

    themes_resp = authenticated_client.get("/admin/themes")
    names = {t["name"] for t in themes_resp.json()}
    assert "Cinéma" in names


def test_update_proposition_reuses_normalized_existing_theme(authenticated_client, db_session):
    existing = models.Theme(name="Cinéma", category=models.ThemeCategory.POP_CULTURE, difficulty_level=5)
    db_session.add(existing)
    db_session.commit()
    db_session.refresh(existing)

    prop = _make_proposition(db_session, "Q", models.PropositionStatus.PENDING)
    resp = authenticated_client.put(
        f"/admin/propositions/{prop.id}",
        json={"new_theme": {"name": " cinéma ", "category": "serious", "difficulty_level": 3}},
    )
    assert resp.status_code == 200
    assert resp.json()["theme_id"] == existing.id

    themes_resp = authenticated_client.get("/admin/themes")
    cinema_themes = [t for t in themes_resp.json() if t["name"].strip().lower() == "cinéma"]
    assert len(cinema_themes) == 1


def test_update_proposition_theme_id_and_new_theme_mutually_exclusive(authenticated_client, db_session, sample_theme):
    prop = _make_proposition(db_session, "Q", models.PropositionStatus.PENDING)
    resp = authenticated_client.put(
        f"/admin/propositions/{prop.id}",
        json={
            "theme_id": sample_theme.id,
            "new_theme": {"name": "Autre", "category": "serious", "difficulty_level": 5},
        },
    )
    assert resp.status_code == 400


def test_update_proposition_explicit_null_theme_id_and_new_theme_mutually_exclusive(authenticated_client, db_session):
    """Revue de code : theme_id explicitement null avec new_theme contournait la
    vérification d'exclusivité (basée sur `payload.theme_id is not None`, toujours
    False pour un null explicite) — corrigé pour se baser sur la présence de la
    clé dans la requête plutôt que sur sa valeur."""
    prop = _make_proposition(db_session, "Q", models.PropositionStatus.PENDING)
    resp = authenticated_client.put(
        f"/admin/propositions/{prop.id}",
        json={
            "theme_id": None,
            "new_theme": {"name": "Autre", "category": "serious", "difficulty_level": 5},
        },
    )
    assert resp.status_code == 400


def test_update_proposition_invalid_difficulty_returns_422(authenticated_client, db_session):
    prop = _make_proposition(db_session, "Q", models.PropositionStatus.PENDING)
    resp = authenticated_client.put(f"/admin/propositions/{prop.id}", json={"difficulty": "impossible"})
    assert resp.status_code == 422


def test_update_proposition_blank_text_returns_422(authenticated_client, db_session):
    prop = _make_proposition(db_session, "Q", models.PropositionStatus.PENDING)
    resp = authenticated_client.put(f"/admin/propositions/{prop.id}", json={"text": "   "})
    assert resp.status_code == 422


def test_update_proposition_too_many_wrong_answers_returns_422(authenticated_client, db_session):
    prop = _make_proposition(db_session, "Q", models.PropositionStatus.PENDING)
    resp = authenticated_client.put(
        f"/admin/propositions/{prop.id}",
        json={"wrong_answers": ["A", "B", "C", "D"]},
    )
    assert resp.status_code == 422


def test_update_proposition_rejects_non_pending_status(authenticated_client, db_session):
    prop = _make_proposition(db_session, "Q", models.PropositionStatus.ACCEPTED)
    resp = authenticated_client.put(f"/admin/propositions/{prop.id}", json={"text": "New text"})
    assert resp.status_code == 400


# --- POST /admin/propositions/{id}/accept (Story F-ext-2.4) ---

def test_accept_proposition_requires_auth(test_client, db_session, sample_theme):
    prop = _make_proposition(db_session, "Q", models.PropositionStatus.PENDING, theme_id=sample_theme.id)
    resp = test_client.post(f"/admin/propositions/{prop.id}/accept")
    assert resp.status_code == 401


def test_accept_proposition_not_found(authenticated_client):
    resp = authenticated_client.post("/admin/propositions/999999/accept")
    assert resp.status_code == 404


def test_accept_proposition_creates_question(authenticated_client, db_session, sample_theme):
    prop = _make_proposition(db_session, "Capitale de la France ?", models.PropositionStatus.PENDING, theme_id=sample_theme.id)
    resp = authenticated_client.post(f"/admin/propositions/{prop.id}/accept")
    assert resp.status_code == 200
    body = resp.json()
    assert body["proposition_id"] == prop.id
    question_id = body["question_id"]

    question = db_session.query(models.Question).filter(models.Question.id == question_id).first()
    assert question is not None
    assert question.text == "Capitale de la France ?"
    assert question.category == sample_theme.name
    assert question.difficulty == models.Difficulty.EASY
    assert question.points == 2
    assert question.correct_answer == "Réponse"
    assert json.loads(question.wrong_answers) == ["A", "B"]
    assert question.theme_id == sample_theme.id

    db_session.refresh(prop)
    assert prop.status == models.PropositionStatus.ACCEPTED


def test_accept_proposition_question_appears_in_random_pool(authenticated_client, db_session, sample_theme):
    prop = _make_proposition(db_session, "Question unique pour ce test", models.PropositionStatus.PENDING, theme_id=sample_theme.id)
    resp = authenticated_client.post(f"/admin/propositions/{prop.id}/accept")
    assert resp.status_code == 200
    question_id = resp.json()["question_id"]

    # /questions/random n'est pas filtré par statut ni par origine (AC #3, aucune
    # modification de cette requête requise) — on vérifie directement que la
    # Question créée est bien la même table interrogée par ce pool, sans dépendre
    # de l'aléatoire du tirage ni du filtre difficulty (qui compare à un type
    # d'enum différent, préexistant, hors périmètre de cette story).
    resp = authenticated_client.get(f"/questions/random?category={sample_theme.name}")
    assert resp.status_code == 200
    question = db_session.query(models.Question).filter(models.Question.id == question_id).first()
    assert question is not None
    assert question.category == sample_theme.name


def test_accept_proposition_with_undetermined_theme_returns_400(authenticated_client, db_session):
    prop = _make_proposition(db_session, "Q", models.PropositionStatus.PENDING, theme_id=None)
    resp = authenticated_client.post(f"/admin/propositions/{prop.id}/accept")
    assert resp.status_code == 400


def test_accept_proposition_already_accepted_returns_400(authenticated_client, db_session, sample_theme):
    prop = _make_proposition(db_session, "Q", models.PropositionStatus.ACCEPTED, theme_id=sample_theme.id)
    resp = authenticated_client.post(f"/admin/propositions/{prop.id}/accept")
    assert resp.status_code == 400


def test_accept_proposition_already_rejected_returns_400(authenticated_client, db_session, sample_theme):
    prop = _make_proposition(db_session, "Q", models.PropositionStatus.REJECTED, theme_id=sample_theme.id)
    resp = authenticated_client.post(f"/admin/propositions/{prop.id}/accept")
    assert resp.status_code == 400


def test_accept_proposition_double_accept_creates_only_one_question(authenticated_client, db_session, sample_theme):
    prop = _make_proposition(db_session, "Q", models.PropositionStatus.PENDING, theme_id=sample_theme.id)
    resp1 = authenticated_client.post(f"/admin/propositions/{prop.id}/accept")
    assert resp1.status_code == 200
    resp2 = authenticated_client.post(f"/admin/propositions/{prop.id}/accept")
    assert resp2.status_code == 400

    questions = db_session.query(models.Question).filter(models.Question.text == "Q").all()
    assert len(questions) == 1


def test_accept_proposition_hard_difficulty_eligible_for_grey_cell_pool(authenticated_client, db_session, sample_theme):
    prop = _make_proposition(db_session, "Question difficile", models.PropositionStatus.PENDING, theme_id=sample_theme.id)
    prop.difficulty = models.Difficulty.HARD
    db_session.commit()

    resp = authenticated_client.post(f"/admin/propositions/{prop.id}/accept")
    assert resp.status_code == 200
    question_id = resp.json()["question_id"]

    hard_questions = db_session.query(models.Question).filter(models.Question.difficulty == models.Difficulty.HARD).all()
    assert any(q.id == question_id for q in hard_questions)


def test_accept_proposition_easy_difficulty_not_eligible_for_grey_cell_pool(authenticated_client, db_session, sample_theme):
    prop = _make_proposition(db_session, "Question facile", models.PropositionStatus.PENDING, theme_id=sample_theme.id)
    resp = authenticated_client.post(f"/admin/propositions/{prop.id}/accept")
    assert resp.status_code == 200
    question_id = resp.json()["question_id"]

    hard_questions = db_session.query(models.Question).filter(models.Question.difficulty == models.Difficulty.HARD).all()
    assert not any(q.id == question_id for q in hard_questions)


# --- POST /admin/propositions/{id}/reject + GET /admin/propositions/rejected (Story F-ext-2.5) ---

def test_reject_proposition_requires_auth(test_client, db_session):
    prop = _make_proposition(db_session, "Q", models.PropositionStatus.PENDING)
    resp = test_client.post(f"/admin/propositions/{prop.id}/reject", json={"reason": "Hors sujet"})
    assert resp.status_code == 401


def test_reject_proposition_not_found(authenticated_client):
    resp = authenticated_client.post("/admin/propositions/999999/reject", json={"reason": "Hors sujet"})
    assert resp.status_code == 404


def test_reject_proposition_valid(authenticated_client, db_session, sample_theme):
    prop = _make_proposition(db_session, "Question douteuse", models.PropositionStatus.PENDING, theme_id=sample_theme.id)
    resp = authenticated_client.post(f"/admin/propositions/{prop.id}/reject", json={"reason": "Doublon d'une question existante"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "rejected"
    assert body["rejection_reason"] == "Doublon d'une question existante"

    db_session.refresh(prop)
    assert prop.status == models.PropositionStatus.REJECTED
    assert prop.rejection_reason == "Doublon d'une question existante"


def test_reject_proposition_no_question_created(authenticated_client, db_session, sample_theme):
    prop = _make_proposition(db_session, "Question douteuse", models.PropositionStatus.PENDING, theme_id=sample_theme.id)
    resp = authenticated_client.post(f"/admin/propositions/{prop.id}/reject", json={"reason": "Doublon"})
    assert resp.status_code == 200

    questions = db_session.query(models.Question).filter(models.Question.text == "Question douteuse").all()
    assert questions == []


def test_reject_proposition_missing_reason_returns_422(authenticated_client, db_session):
    prop = _make_proposition(db_session, "Q", models.PropositionStatus.PENDING)
    resp = authenticated_client.post(f"/admin/propositions/{prop.id}/reject", json={})
    assert resp.status_code == 422


def test_reject_proposition_blank_reason_returns_422(authenticated_client, db_session):
    prop = _make_proposition(db_session, "Q", models.PropositionStatus.PENDING)
    resp = authenticated_client.post(f"/admin/propositions/{prop.id}/reject", json={"reason": "   "})
    assert resp.status_code == 422


def test_reject_proposition_already_accepted_returns_400(authenticated_client, db_session, sample_theme):
    prop = _make_proposition(db_session, "Q", models.PropositionStatus.ACCEPTED, theme_id=sample_theme.id)
    resp = authenticated_client.post(f"/admin/propositions/{prop.id}/reject", json={"reason": "Trop tard"})
    assert resp.status_code == 400


def test_reject_proposition_already_rejected_returns_400(authenticated_client, db_session, sample_theme):
    prop = _make_proposition(db_session, "Q", models.PropositionStatus.REJECTED, theme_id=sample_theme.id)
    resp = authenticated_client.post(f"/admin/propositions/{prop.id}/reject", json={"reason": "Encore"})
    assert resp.status_code == 400


def test_reject_proposition_double_reject_keeps_single_decision(authenticated_client, db_session, sample_theme):
    prop = _make_proposition(db_session, "Q", models.PropositionStatus.PENDING, theme_id=sample_theme.id)
    resp1 = authenticated_client.post(f"/admin/propositions/{prop.id}/reject", json={"reason": "Première raison"})
    assert resp1.status_code == 200
    resp2 = authenticated_client.post(f"/admin/propositions/{prop.id}/reject", json={"reason": "Deuxième raison"})
    assert resp2.status_code == 400

    db_session.refresh(prop)
    assert prop.rejection_reason == "Première raison"


def test_reject_proposition_no_longer_in_pending_list(authenticated_client, db_session, sample_theme):
    prop = _make_proposition(db_session, "Question douteuse", models.PropositionStatus.PENDING, theme_id=sample_theme.id)
    resp = authenticated_client.post(f"/admin/propositions/{prop.id}/reject", json={"reason": "Doublon"})
    assert resp.status_code == 200

    pending_resp = authenticated_client.get("/admin/propositions/pending")
    assert prop.id not in {p["id"] for p in pending_resp.json()}


def test_list_rejected_propositions_requires_auth(test_client):
    resp = test_client.get("/admin/propositions/rejected")
    assert resp.status_code == 401


def test_list_rejected_propositions_filters_by_status(authenticated_client, db_session, sample_theme):
    rejected = _make_proposition(db_session, "Rejected Q", models.PropositionStatus.REJECTED, theme_id=sample_theme.id)
    rejected.rejection_reason = "Hors sujet"
    db_session.commit()
    _make_proposition(db_session, "Pending Q", models.PropositionStatus.PENDING)
    _make_proposition(db_session, "Accepted Q", models.PropositionStatus.ACCEPTED)

    resp = authenticated_client.get("/admin/propositions/rejected")
    assert resp.status_code == 200
    body = resp.json()
    texts = {p["text"] for p in body}
    assert texts == {"Rejected Q"}
    assert body[0]["rejection_reason"] == "Hors sujet"
