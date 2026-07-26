"""
Tests pour le router admin (Epic F, story F.1) : CRUD thèmes/questions,
validation de cohérence, export/import, statistiques d'utilisation.
"""
import json


def _theme_payload(name="Nouveau thème"):
    return {
        "name": name,
        "category": "serious",
        "difficulty_level": 5,
        "description": "Un thème de test",
    }


def _question_payload(theme_id=None, text="Quelle est la capitale de la France ?"):
    return {
        "text": text,
        "category": "Géographie",
        "difficulty": "easy",
        "points": 2,
        "correct_answer": "Paris",
        "wrong_answers": ["Londres", "Berlin", "Madrid"],
        "theme_id": theme_id,
        "question_number": 1,
    }


# --- Thèmes CRUD ---

def test_create_and_get_theme(test_client):
    resp = test_client.post("/admin/themes", json=_theme_payload())
    assert resp.status_code == 200
    theme = resp.json()
    assert theme["name"] == "Nouveau thème"
    assert theme["category"] == "serious"

    resp = test_client.get(f"/admin/themes/{theme['id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == theme["id"]


def test_list_themes(test_client):
    test_client.post("/admin/themes", json=_theme_payload("Thème A"))
    test_client.post("/admin/themes", json=_theme_payload("Thème B"))
    resp = test_client.get("/admin/themes")
    assert resp.status_code == 200
    names = [t["name"] for t in resp.json()]
    assert "Thème A" in names and "Thème B" in names


def test_get_theme_404(test_client):
    resp = test_client.get("/admin/themes/999999")
    assert resp.status_code == 404


def test_update_theme(test_client):
    theme = test_client.post("/admin/themes", json=_theme_payload()).json()
    resp = test_client.put(f"/admin/themes/{theme['id']}", json={"description": "Description mise à jour"})
    assert resp.status_code == 200
    assert resp.json()["description"] == "Description mise à jour"
    assert resp.json()["name"] == theme["name"]  # champs non fournis inchangés


def test_update_theme_404(test_client):
    resp = test_client.put("/admin/themes/999999", json={"description": "x"})
    assert resp.status_code == 404


def test_delete_theme(test_client):
    theme = test_client.post("/admin/themes", json=_theme_payload()).json()
    resp = test_client.delete(f"/admin/themes/{theme['id']}")
    assert resp.status_code == 200
    assert resp.json()["deleted_theme_id"] == theme["id"]
    assert test_client.get(f"/admin/themes/{theme['id']}").status_code == 404


def test_delete_theme_404(test_client):
    resp = test_client.delete("/admin/themes/999999")
    assert resp.status_code == 404


# --- Questions CRUD ---

def test_create_and_get_question(test_client):
    theme = test_client.post("/admin/themes", json=_theme_payload()).json()
    resp = test_client.post("/admin/questions", json=_question_payload(theme_id=theme["id"]))
    assert resp.status_code == 200
    question = resp.json()
    assert question["text"].startswith("Quelle est")
    assert question["wrong_answers"] == ["Londres", "Berlin", "Madrid"]

    resp = test_client.get(f"/admin/questions/{question['id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == question["id"]


def test_list_questions_filtered_by_theme(test_client):
    theme = test_client.post("/admin/themes", json=_theme_payload()).json()
    other_theme = test_client.post("/admin/themes", json=_theme_payload("Autre")).json()
    test_client.post("/admin/questions", json=_question_payload(theme_id=theme["id"], text="Q1"))
    test_client.post("/admin/questions", json=_question_payload(theme_id=other_theme["id"], text="Q2"))

    resp = test_client.get(f"/admin/questions?theme_id={theme['id']}")
    assert resp.status_code == 200
    texts = [q["text"] for q in resp.json()]
    assert texts == ["Q1"]


def test_update_question(test_client):
    question = test_client.post("/admin/questions", json=_question_payload()).json()
    resp = test_client.put(f"/admin/questions/{question['id']}", json={"correct_answer": "Lyon"})
    assert resp.status_code == 200
    assert resp.json()["correct_answer"] == "Lyon"


def test_delete_question_404(test_client):
    resp = test_client.delete("/admin/questions/999999")
    assert resp.status_code == 404


def test_delete_question_no_theme(test_client):
    question = test_client.post("/admin/questions", json=_question_payload(theme_id=None)).json()
    resp = test_client.delete(f"/admin/questions/{question['id']}")
    assert resp.status_code == 200
    assert resp.json()["warning"] is None


# --- AC #3 : validation de cohérence (seuil 10 questions/thème) ---

def test_delete_question_below_threshold_warns(test_client):
    theme = test_client.post("/admin/themes", json=_theme_payload()).json()
    question = test_client.post(
        "/admin/questions", json=_question_payload(theme_id=theme["id"])
    ).json()

    resp = test_client.delete(f"/admin/questions/{question['id']}")
    assert resp.status_code == 200
    warning = resp.json()["warning"]
    assert warning is not None
    assert warning["theme_id"] == theme["id"]
    assert warning["question_count"] == 0


def test_delete_theme_with_questions_warns_and_orphans_them(test_client):
    # Régression : même avec un thème LARGEMENT au-dessus du seuil de 10, le
    # supprimer orpheline toutes ses questions (theme_id -> None). L'ancien
    # comportement ne le signalait que si le thème était déjà sous le seuil,
    # ratant justement le cas le plus destructeur (12 questions perdues sans
    # avertissement).
    theme = test_client.post("/admin/themes", json=_theme_payload()).json()
    question_ids = []
    for i in range(12):
        q = test_client.post(
            "/admin/questions", json=_question_payload(theme_id=theme["id"], text=f"Q{i}")
        ).json()
        question_ids.append(q["id"])

    resp = test_client.delete(f"/admin/themes/{theme['id']}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["warning"] is not None
    assert body["warning"]["question_count"] == 12

    # Les questions ne sont pas supprimées, elles sont orphelines.
    for qid in question_ids:
        q = test_client.get(f"/admin/questions/{qid}").json()
        assert q["theme_id"] is None


def test_delete_theme_without_questions_no_warning(test_client):
    theme = test_client.post("/admin/themes", json=_theme_payload()).json()
    resp = test_client.delete(f"/admin/themes/{theme['id']}")
    assert resp.status_code == 200
    assert resp.json()["warning"] is None


def test_delete_question_at_or_above_threshold_no_warning(test_client, sample_theme, sample_questions_for_theme):
    # sample_questions_for_theme crée 10 questions -> suppression d'une seule reste à 9,
    # donc l'avertissement doit apparaître ; on vérifie l'inverse en ajoutant une 11e question.
    extra = test_client.post(
        "/admin/questions", json=_question_payload(theme_id=sample_theme.id, text="Question supplémentaire")
    ).json()
    resp = test_client.delete(f"/admin/questions/{extra['id']}")
    assert resp.status_code == 200
    assert resp.json()["warning"] is None  # reste à 10, au seuil, pas d'avertissement


# --- Statistiques d'utilisation (AC #5) ---

def test_question_stats_no_answers(test_client):
    question = test_client.post("/admin/questions", json=_question_payload()).json()
    resp = test_client.get(f"/admin/questions/{question['id']}/stats")
    assert resp.status_code == 200
    stats = resp.json()
    assert stats == {
        "question_id": question["id"],
        "times_answered": 0,
        "correct_answers": 0,
        "success_rate": 0.0,
    }


def test_question_stats_with_answers(test_client, db_session, sample_team, sample_question):
    from app import models

    db_session.add_all([
        models.Answer(question_id=sample_question.id, team_id=sample_team.id, player_answer="Paris", is_correct=True, points_earned=2),
        models.Answer(question_id=sample_question.id, team_id=sample_team.id, player_answer="Berlin", is_correct=False, points_earned=0),
    ])
    db_session.commit()

    resp = test_client.get(f"/admin/questions/{sample_question.id}/stats")
    assert resp.status_code == 200
    stats = resp.json()
    assert stats["times_answered"] == 2
    assert stats["correct_answers"] == 1
    assert stats["success_rate"] == 0.5


def test_question_stats_404(test_client):
    resp = test_client.get("/admin/questions/999999/stats")
    assert resp.status_code == 404


# --- Export / Import (AC #4) ---

def test_export_content(test_client):
    theme = test_client.post("/admin/themes", json=_theme_payload()).json()
    test_client.post("/admin/questions", json=_question_payload(theme_id=theme["id"]))

    resp = test_client.get("/admin/content/export")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["themes"]) == 1
    assert len(data["questions"]) == 1


def test_import_content(test_client):
    payload = {
        "themes": [_theme_payload("Importé")],
        "questions": [_question_payload(theme_id=None, text="Question importée")],
    }
    resp = test_client.post("/admin/content/import", json=payload)
    assert resp.status_code == 200
    result = resp.json()
    assert result["themes_created"] == 1
    assert result["questions_created"] == 1

    resp = test_client.get("/admin/themes")
    assert any(t["name"] == "Importé" for t in resp.json())


def test_import_invalid_entry_inserts_nothing(test_client):
    payload = {
        "themes": [{"name": "x", "category": "not-a-real-category", "difficulty_level": 5}],
        "questions": [],
    }
    resp = test_client.post("/admin/content/import", json=payload)
    assert resp.status_code == 422  # validation Pydantic échoue avant tout insert

    resp = test_client.get("/admin/themes")
    assert resp.json() == []


def test_export_import_round_trip(test_client):
    theme = test_client.post("/admin/themes", json=_theme_payload("Round trip")).json()
    test_client.post("/admin/questions", json=_question_payload(theme_id=theme["id"], text="RT question"))

    exported = test_client.get("/admin/content/export").json()

    # Reformater l'export (contient des ids/created_at) en payload d'import (ThemeCreate/QuestionCreate)
    import_payload = {
        "themes": [
            {"name": t["name"] + " (copie)", "category": t["category"], "difficulty_level": t["difficulty_level"], "description": t["description"]}
            for t in exported["themes"]
        ],
        "questions": [],
    }
    resp = test_client.post("/admin/content/import", json=import_payload)
    assert resp.status_code == 200
    assert resp.json()["themes_created"] == 1


def test_export_import_round_trip_remaps_question_theme_id(test_client):
    # Régression : réimporter un export entier (thème + questions) doit rattacher
    # les questions au NOUVEL id de thème, pas à l'ancien (périmé, puisque
    # l'import crée toujours un nouveau thème avec un nouvel id).
    theme = test_client.post("/admin/themes", json=_theme_payload("Original")).json()
    test_client.post("/admin/questions", json=_question_payload(theme_id=theme["id"], text="Q remap"))

    exported = test_client.get("/admin/content/export").json()
    import_payload = {
        "themes": [
            {
                "source_id": t["id"],
                "name": t["name"] + " (v2)",
                "category": t["category"],
                "difficulty_level": t["difficulty_level"],
                "description": t["description"],
            }
            for t in exported["themes"]
        ],
        "questions": [
            {
                "text": q["text"],
                "category": q["category"],
                "difficulty": q["difficulty"],
                "points": q["points"],
                "correct_answer": q["correct_answer"],
                "wrong_answers": q["wrong_answers"],
                "theme_id": q["theme_id"],
                "question_number": q["question_number"],
            }
            for q in exported["questions"]
        ],
    }
    resp = test_client.post("/admin/content/import", json=import_payload)
    assert resp.status_code == 200

    new_theme = next(t for t in test_client.get("/admin/themes").json() if t["name"] == "Original (v2)")
    new_questions = test_client.get(f"/admin/questions?theme_id={new_theme['id']}").json()
    assert any(q["text"] == "Q remap" for q in new_questions)


# --- Robustesse (revue de code) ---

def test_create_question_with_unknown_theme_id_404s(test_client):
    resp = test_client.post("/admin/questions", json=_question_payload(theme_id=999999))
    assert resp.status_code == 404


def test_update_question_with_unknown_theme_id_404s(test_client):
    question = test_client.post("/admin/questions", json=_question_payload()).json()
    resp = test_client.put(f"/admin/questions/{question['id']}", json={"theme_id": 999999})
    assert resp.status_code == 404


def test_create_theme_duplicate_name_returns_400_not_500(test_client):
    test_client.post("/admin/themes", json=_theme_payload("Doublon"))
    resp = test_client.post("/admin/themes", json=_theme_payload("Doublon"))
    assert resp.status_code == 400


def test_update_question_difficulty_resyncs_points(test_client):
    question = test_client.post("/admin/questions", json=_question_payload()).json()
    assert question["difficulty"] == "easy" and question["points"] == 2

    resp = test_client.put(f"/admin/questions/{question['id']}", json={"difficulty": "hard"})
    assert resp.status_code == 200
    updated = resp.json()
    assert updated["difficulty"] == "hard"
    assert updated["points"] == 6


def test_update_question_difficulty_with_explicit_points_respects_it(test_client):
    question = test_client.post("/admin/questions", json=_question_payload()).json()
    resp = test_client.put(f"/admin/questions/{question['id']}", json={"difficulty": "hard", "points": 4})
    assert resp.status_code == 200
    assert resp.json()["points"] == 4
