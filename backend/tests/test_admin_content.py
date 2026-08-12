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

def test_create_and_get_theme(authenticated_client):
    resp = authenticated_client.post("/admin/themes", json=_theme_payload())
    assert resp.status_code == 200
    theme = resp.json()
    assert theme["name"] == "Nouveau thème"
    assert theme["category"] == "serious"

    resp = authenticated_client.get(f"/admin/themes/{theme['id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == theme["id"]


def test_list_themes(authenticated_client):
    authenticated_client.post("/admin/themes", json=_theme_payload("Thème A"))
    authenticated_client.post("/admin/themes", json=_theme_payload("Thème B"))
    resp = authenticated_client.get("/admin/themes")
    assert resp.status_code == 200
    names = [t["name"] for t in resp.json()]
    assert "Thème A" in names and "Thème B" in names


def test_get_theme_404(authenticated_client):
    resp = authenticated_client.get("/admin/themes/999999")
    assert resp.status_code == 404


def test_update_theme(authenticated_client):
    theme = authenticated_client.post("/admin/themes", json=_theme_payload()).json()
    resp = authenticated_client.put(f"/admin/themes/{theme['id']}", json={"description": "Description mise à jour"})
    assert resp.status_code == 200
    assert resp.json()["description"] == "Description mise à jour"
    assert resp.json()["name"] == theme["name"]  # champs non fournis inchangés


def test_update_theme_404(authenticated_client):
    resp = authenticated_client.put("/admin/themes/999999", json={"description": "x"})
    assert resp.status_code == 404


def test_delete_theme(authenticated_client):
    theme = authenticated_client.post("/admin/themes", json=_theme_payload()).json()
    resp = authenticated_client.delete(f"/admin/themes/{theme['id']}")
    assert resp.status_code == 200
    assert resp.json()["deleted_theme_id"] == theme["id"]
    assert authenticated_client.get(f"/admin/themes/{theme['id']}").status_code == 404


def test_delete_theme_404(authenticated_client):
    resp = authenticated_client.delete("/admin/themes/999999")
    assert resp.status_code == 404


# --- Questions CRUD ---

def test_create_and_get_question(authenticated_client):
    theme = authenticated_client.post("/admin/themes", json=_theme_payload()).json()
    resp = authenticated_client.post("/admin/questions", json=_question_payload(theme_id=theme["id"]))
    assert resp.status_code == 200
    question = resp.json()
    assert question["text"].startswith("Quelle est")
    assert question["wrong_answers"] == ["Londres", "Berlin", "Madrid"]

    resp = authenticated_client.get(f"/admin/questions/{question['id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == question["id"]


def test_list_questions_filtered_by_theme(authenticated_client):
    theme = authenticated_client.post("/admin/themes", json=_theme_payload()).json()
    other_theme = authenticated_client.post("/admin/themes", json=_theme_payload("Autre")).json()
    authenticated_client.post("/admin/questions", json=_question_payload(theme_id=theme["id"], text="Q1"))
    authenticated_client.post("/admin/questions", json=_question_payload(theme_id=other_theme["id"], text="Q2"))

    resp = authenticated_client.get(f"/admin/questions?theme_id={theme['id']}")
    assert resp.status_code == 200
    texts = [q["text"] for q in resp.json()]
    assert texts == ["Q1"]


def test_update_question(authenticated_client):
    question = authenticated_client.post("/admin/questions", json=_question_payload()).json()
    resp = authenticated_client.put(f"/admin/questions/{question['id']}", json={"correct_answer": "Lyon"})
    assert resp.status_code == 200
    assert resp.json()["correct_answer"] == "Lyon"


def test_delete_question_404(authenticated_client):
    resp = authenticated_client.delete("/admin/questions/999999")
    assert resp.status_code == 404


def test_delete_question_no_theme(authenticated_client):
    question = authenticated_client.post("/admin/questions", json=_question_payload(theme_id=None)).json()
    resp = authenticated_client.delete(f"/admin/questions/{question['id']}")
    assert resp.status_code == 200
    assert resp.json()["warning"] is None


# --- AC #3 : validation de cohérence (seuil 10 questions/thème) ---

def test_delete_question_below_threshold_warns(authenticated_client):
    theme = authenticated_client.post("/admin/themes", json=_theme_payload()).json()
    question = authenticated_client.post(
        "/admin/questions", json=_question_payload(theme_id=theme["id"])
    ).json()

    resp = authenticated_client.delete(f"/admin/questions/{question['id']}")
    assert resp.status_code == 200
    warning = resp.json()["warning"]
    assert warning is not None
    assert warning["theme_id"] == theme["id"]
    assert warning["question_count"] == 0


def test_delete_theme_with_questions_warns_and_orphans_them(authenticated_client):
    # Régression : même avec un thème LARGEMENT au-dessus du seuil de 10, le
    # supprimer orpheline toutes ses questions (theme_id -> None). L'ancien
    # comportement ne le signalait que si le thème était déjà sous le seuil,
    # ratant justement le cas le plus destructeur (12 questions perdues sans
    # avertissement).
    theme = authenticated_client.post("/admin/themes", json=_theme_payload()).json()
    question_ids = []
    for i in range(12):
        q = authenticated_client.post(
            "/admin/questions", json=_question_payload(theme_id=theme["id"], text=f"Q{i}")
        ).json()
        question_ids.append(q["id"])

    resp = authenticated_client.delete(f"/admin/themes/{theme['id']}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["warning"] is not None
    assert body["warning"]["question_count"] == 12

    # Les questions ne sont pas supprimées, elles sont orphelines.
    for qid in question_ids:
        q = authenticated_client.get(f"/admin/questions/{qid}").json()
        assert q["theme_id"] is None


def test_delete_theme_without_questions_no_warning(authenticated_client):
    theme = authenticated_client.post("/admin/themes", json=_theme_payload()).json()
    resp = authenticated_client.delete(f"/admin/themes/{theme['id']}")
    assert resp.status_code == 200
    assert resp.json()["warning"] is None


def test_delete_question_at_or_above_threshold_no_warning(authenticated_client, sample_theme, sample_questions_for_theme):
    # sample_questions_for_theme crée 10 questions -> suppression d'une seule reste à 9,
    # donc l'avertissement doit apparaître ; on vérifie l'inverse en ajoutant une 11e question.
    extra = authenticated_client.post(
        "/admin/questions", json=_question_payload(theme_id=sample_theme.id, text="Question supplémentaire")
    ).json()
    resp = authenticated_client.delete(f"/admin/questions/{extra['id']}")
    assert resp.status_code == 200
    assert resp.json()["warning"] is None  # reste à 10, au seuil, pas d'avertissement


# --- Statistiques d'utilisation (AC #5) ---

def test_question_stats_no_answers(authenticated_client):
    question = authenticated_client.post("/admin/questions", json=_question_payload()).json()
    resp = authenticated_client.get(f"/admin/questions/{question['id']}/stats")
    assert resp.status_code == 200
    stats = resp.json()
    assert stats == {
        "question_id": question["id"],
        "times_answered": 0,
        "correct_answers": 0,
        "success_rate": 0.0,
    }


def test_question_stats_with_answers(authenticated_client, db_session, sample_team, sample_question):
    from app import models

    # Une équipe ne répond qu'une fois par question (contrainte unique
    # question_id+team_id, BUG-110) : il faut 2 équipes distinctes ici.
    other_team = models.Team(name="Other Team", game_session_id=sample_team.game_session_id, score=0)
    db_session.add(other_team)
    db_session.commit()
    db_session.refresh(other_team)

    db_session.add_all([
        models.Answer(question_id=sample_question.id, team_id=sample_team.id, player_answer="Paris", is_correct=True, points_earned=2),
        models.Answer(question_id=sample_question.id, team_id=other_team.id, player_answer="Berlin", is_correct=False, points_earned=0),
    ])
    db_session.commit()

    resp = authenticated_client.get(f"/admin/questions/{sample_question.id}/stats")
    assert resp.status_code == 200
    stats = resp.json()
    assert stats["times_answered"] == 2
    assert stats["correct_answers"] == 1
    assert stats["success_rate"] == 0.5


def test_question_stats_404(authenticated_client):
    resp = authenticated_client.get("/admin/questions/999999/stats")
    assert resp.status_code == 404


def test_all_question_stats_aggregates_by_question(authenticated_client, db_session, sample_team, sample_question, sample_theme):
    from app import models

    other_team = models.Team(name="Other Team 2", game_session_id=sample_team.game_session_id, score=0)
    db_session.add(other_team)
    db_session.commit()
    db_session.refresh(other_team)

    db_session.add_all([
        models.Answer(question_id=sample_question.id, team_id=sample_team.id, player_answer="Paris", is_correct=True, points_earned=2),
        models.Answer(question_id=sample_question.id, team_id=other_team.id, player_answer="Berlin", is_correct=False, points_earned=0),
    ])
    db_session.commit()

    resp = authenticated_client.get("/admin/stats/questions")
    assert resp.status_code == 200
    body = resp.json()
    row = next(r for r in body if r["question_id"] == sample_question.id)
    assert row["theme_id"] == sample_theme.id
    assert row["theme_name"] == sample_theme.name
    assert row["times_answered"] == 2
    assert row["correct_answers"] == 1
    assert row["success_rate"] == 0.5

    # Une question jamais répondue apparaît quand même, à 0 sans division par zéro.
    unanswered = authenticated_client.post("/admin/questions", json=_question_payload(text="Jamais répondue")).json()
    resp2 = authenticated_client.get("/admin/stats/questions")
    row2 = next(r for r in resp2.json() if r["question_id"] == unanswered["id"])
    assert row2["times_answered"] == 0
    assert row2["success_rate"] == 0.0


def test_theme_stats_aggregates_across_questions(authenticated_client, db_session, sample_team, sample_question, sample_theme):
    from app import models

    other_team = models.Team(name="Other Team 3", game_session_id=sample_team.game_session_id, score=0)
    db_session.add(other_team)
    db_session.commit()
    db_session.refresh(other_team)

    db_session.add_all([
        models.Answer(question_id=sample_question.id, team_id=sample_team.id, player_answer="Paris", is_correct=True, points_earned=2),
        models.Answer(question_id=sample_question.id, team_id=other_team.id, player_answer="Berlin", is_correct=False, points_earned=0),
    ])
    db_session.commit()

    resp = authenticated_client.get("/admin/stats/themes")
    assert resp.status_code == 200
    row = next(r for r in resp.json() if r["theme_id"] == sample_theme.id)
    assert row["times_answered"] == 2
    assert row["correct_answers"] == 1
    assert row["success_rate"] == 0.5
    assert row["questions_count"] >= 1


def test_theme_stats_includes_theme_with_no_questions(authenticated_client):
    theme = authenticated_client.post(
        "/admin/themes", json={"name": "Thème vide stats", "category": "serious", "difficulty_level": 5}
    ).json()

    resp = authenticated_client.get("/admin/stats/themes")
    assert resp.status_code == 200
    row = next(r for r in resp.json() if r["theme_id"] == theme["id"])
    assert row["questions_count"] == 0
    assert row["times_answered"] == 0
    assert row["success_rate"] == 0.0


# --- Export / Import (AC #4) ---

def test_export_content(authenticated_client):
    theme = authenticated_client.post("/admin/themes", json=_theme_payload()).json()
    authenticated_client.post("/admin/questions", json=_question_payload(theme_id=theme["id"]))

    resp = authenticated_client.get("/admin/content/export")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["themes"]) == 1
    assert len(data["questions"]) == 1


def test_import_content(authenticated_client):
    payload = {
        "themes": [_theme_payload("Importé")],
        "questions": [_question_payload(theme_id=None, text="Question importée")],
    }
    resp = authenticated_client.post("/admin/content/import", json=payload)
    assert resp.status_code == 200
    result = resp.json()
    assert result["themes_created"] == 1
    assert result["questions_created"] == 1

    resp = authenticated_client.get("/admin/themes")
    assert any(t["name"] == "Importé" for t in resp.json())


def test_import_invalid_entry_inserts_nothing(authenticated_client):
    payload = {
        "themes": [{"name": "x", "category": "not-a-real-category", "difficulty_level": 5}],
        "questions": [],
    }
    resp = authenticated_client.post("/admin/content/import", json=payload)
    assert resp.status_code == 422  # validation Pydantic échoue avant tout insert

    resp = authenticated_client.get("/admin/themes")
    assert resp.json() == []


def test_export_import_round_trip(authenticated_client):
    theme = authenticated_client.post("/admin/themes", json=_theme_payload("Round trip")).json()
    authenticated_client.post("/admin/questions", json=_question_payload(theme_id=theme["id"], text="RT question"))

    exported = authenticated_client.get("/admin/content/export").json()

    # Reformater l'export (contient des ids/created_at) en payload d'import (ThemeCreate/QuestionCreate)
    import_payload = {
        "themes": [
            {"name": t["name"] + " (copie)", "category": t["category"], "difficulty_level": t["difficulty_level"], "description": t["description"]}
            for t in exported["themes"]
        ],
        "questions": [],
    }
    resp = authenticated_client.post("/admin/content/import", json=import_payload)
    assert resp.status_code == 200
    assert resp.json()["themes_created"] == 1


def test_export_import_round_trip_remaps_question_theme_id(authenticated_client):
    # Régression : réimporter un export entier (thème + questions) doit rattacher
    # les questions au NOUVEL id de thème, pas à l'ancien (périmé, puisque
    # l'import crée toujours un nouveau thème avec un nouvel id).
    theme = authenticated_client.post("/admin/themes", json=_theme_payload("Original")).json()
    authenticated_client.post("/admin/questions", json=_question_payload(theme_id=theme["id"], text="Q remap"))

    exported = authenticated_client.get("/admin/content/export").json()
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
    resp = authenticated_client.post("/admin/content/import", json=import_payload)
    assert resp.status_code == 200

    new_theme = next(t for t in authenticated_client.get("/admin/themes").json() if t["name"] == "Original (v2)")
    new_questions = authenticated_client.get(f"/admin/questions?theme_id={new_theme['id']}").json()
    assert any(q["text"] == "Q remap" for q in new_questions)


# --- Robustesse (revue de code) ---

def test_create_question_with_unknown_theme_id_404s(authenticated_client):
    resp = authenticated_client.post("/admin/questions", json=_question_payload(theme_id=999999))
    assert resp.status_code == 404


def test_update_question_with_unknown_theme_id_404s(authenticated_client):
    question = authenticated_client.post("/admin/questions", json=_question_payload()).json()
    resp = authenticated_client.put(f"/admin/questions/{question['id']}", json={"theme_id": 999999})
    assert resp.status_code == 404


def test_create_theme_duplicate_name_returns_400_not_500(authenticated_client):
    authenticated_client.post("/admin/themes", json=_theme_payload("Doublon"))
    resp = authenticated_client.post("/admin/themes", json=_theme_payload("Doublon"))
    assert resp.status_code == 400


def test_update_question_difficulty_resyncs_points(authenticated_client):
    question = authenticated_client.post("/admin/questions", json=_question_payload()).json()
    assert question["difficulty"] == "easy" and question["points"] == 2

    resp = authenticated_client.put(f"/admin/questions/{question['id']}", json={"difficulty": "hard"})
    assert resp.status_code == 200
    updated = resp.json()
    assert updated["difficulty"] == "hard"
    assert updated["points"] == 6


def test_update_question_difficulty_with_explicit_points_respects_it(authenticated_client):
    question = authenticated_client.post("/admin/questions", json=_question_payload()).json()
    resp = authenticated_client.put(f"/admin/questions/{question['id']}", json={"difficulty": "hard", "points": 4})
    assert resp.status_code == 200
    assert resp.json()["points"] == 4
