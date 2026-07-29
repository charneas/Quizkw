"""
Tests pour le endpoint public de soumission de propositions (Epic F-ext,
Story F-ext-1.1). Endpoint non authentifié par conception (FR1).
"""
from app import models


def _proposition_payload(theme_id=None, text="Quelle est la capitale de la France ?"):
    return {
        "text": text,
        "correct_answer": "Paris",
        "wrong_answers": ["Londres", "Berlin", "Madrid"],
        "theme_id": theme_id,
        "difficulty": "easy",
    }


def test_create_proposition_with_theme(test_client, sample_theme):
    resp = test_client.post("/propositions", json=_proposition_payload(theme_id=sample_theme.id))
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "pending"
    assert body["theme_id"] == sample_theme.id
    assert body["wrong_answers"] == ["Londres", "Berlin", "Madrid"]


def test_create_proposition_without_theme(test_client):
    resp = test_client.post("/propositions", json=_proposition_payload(theme_id=None))
    assert resp.status_code == 200
    body = resp.json()
    assert body["theme_id"] is None
    assert body["status"] == "pending"


def test_create_proposition_missing_question(test_client):
    payload = _proposition_payload()
    del payload["text"]
    resp = test_client.post("/propositions", json=payload)
    assert resp.status_code == 422
    assert "detail" in resp.json()


def test_list_themes_for_proposition_no_auth_required(test_client, sample_theme):
    resp = test_client.get("/propositions/themes")
    assert resp.status_code == 200
    names = {t["name"] for t in resp.json()}
    assert sample_theme.name in names


def test_list_themes_for_proposition_empty(test_client):
    resp = test_client.get("/propositions/themes")
    assert resp.status_code == 200
    assert resp.json() == []


def test_create_proposition_missing_correct_answer(test_client):
    payload = _proposition_payload()
    del payload["correct_answer"]
    resp = test_client.post("/propositions", json=payload)
    assert resp.status_code == 422


def test_create_proposition_missing_difficulty(test_client):
    payload = _proposition_payload()
    del payload["difficulty"]
    resp = test_client.post("/propositions", json=payload)
    assert resp.status_code == 422


def test_create_proposition_invalid_difficulty(test_client):
    payload = _proposition_payload()
    payload["difficulty"] = "impossible"
    resp = test_client.post("/propositions", json=payload)
    assert resp.status_code == 422


def test_create_proposition_text_too_long(test_client):
    payload = _proposition_payload()
    payload["text"] = "a" * 501
    resp = test_client.post("/propositions", json=payload)
    assert resp.status_code == 422


def test_create_proposition_too_many_wrong_answers(test_client):
    payload = _proposition_payload()
    payload["wrong_answers"] = ["a", "b", "c", "d"]
    resp = test_client.post("/propositions", json=payload)
    assert resp.status_code == 422


def test_create_proposition_blank_text(test_client):
    payload = _proposition_payload()
    payload["text"] = "   "
    resp = test_client.post("/propositions", json=payload)
    assert resp.status_code == 422


def test_create_proposition_blank_correct_answer(test_client):
    payload = _proposition_payload()
    payload["correct_answer"] = "   "
    resp = test_client.post("/propositions", json=payload)
    assert resp.status_code == 422


def test_create_proposition_correct_answer_too_long(test_client):
    payload = _proposition_payload()
    payload["correct_answer"] = "a" * 201
    resp = test_client.post("/propositions", json=payload)
    assert resp.status_code == 422


def test_create_proposition_wrong_answer_too_long(test_client):
    payload = _proposition_payload()
    payload["wrong_answers"] = ["a" * 201]
    resp = test_client.post("/propositions", json=payload)
    assert resp.status_code == 422


def test_create_proposition_no_wrong_answers(test_client):
    payload = _proposition_payload()
    payload["wrong_answers"] = []
    resp = test_client.post("/propositions", json=payload)
    assert resp.status_code == 200
    assert resp.json()["wrong_answers"] == []


def test_create_proposition_unknown_theme_404(test_client):
    resp = test_client.post("/propositions", json=_proposition_payload(theme_id=999999))
    assert resp.status_code == 404
    assert "detail" in resp.json()


def test_proposition_never_appears_in_question_pool(test_client, db_session, sample_question):
    questions_before = db_session.query(models.Question).count()

    resp = test_client.post(
        "/propositions",
        json=_proposition_payload(text="Une proposition tout juste soumise, jamais une Question"),
    )
    assert resp.status_code == 200

    questions_after = db_session.query(models.Question).count()
    assert questions_after == questions_before

    # Une Question existe déjà (sample_question) : /questions/random doit
    # toujours la retourner, et jamais le texte de la proposition tout juste
    # soumise, quel que soit le nombre de tirages.
    for _ in range(10):
        random_resp = test_client.get("/questions/random")
        assert random_resp.status_code == 200
        question = random_resp.json()["question"]
        assert question["text"] != "Une proposition tout juste soumise, jamais une Question"
        assert question["id"] == sample_question.id
