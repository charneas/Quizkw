"""
Tests pour le router de génération de contenu (Epic F, story F.2).

Le client Wikipedia et le client Anthropic sont mockés (monkeypatch des
fonctions importées dans main_content_gen) : aucun appel réseau réel, aucune
consommation de crédits API pendant la suite pytest (voir Dev Notes de la story).
"""
import pytest

import main_content_gen
from app.schemas_content_gen import GeneratedContent, GeneratedQuestion
from app.schemas import ThemeCategoryEnum, DifficultyEnum


def _fake_generated_content(category=ThemeCategoryEnum.serious, n=2):
    return GeneratedContent(
        theme_name="Histoire de France",
        category=category,
        questions=[
            GeneratedQuestion(
                text=f"Question {i}",
                correct_answer=f"Réponse {i}",
                wrong_answers=["a", "b", "c"],
                difficulty=DifficultyEnum.easy,
            )
            for i in range(n)
        ],
    )


@pytest.fixture
def mock_wikipedia(monkeypatch):
    monkeypatch.setattr(main_content_gen, "get_wikipedia_extract", lambda topic: f"Extrait sur {topic}.")


@pytest.fixture
def mock_wikipedia_not_found(monkeypatch):
    def _raise(topic):
        raise LookupError(f"Sujet introuvable : {topic}")
    monkeypatch.setattr(main_content_gen, "get_wikipedia_extract", _raise)


@pytest.fixture
def mock_generate_content(monkeypatch):
    monkeypatch.setattr(main_content_gen, "generate_content", lambda topic, extract, category: _fake_generated_content(category or ThemeCategoryEnum.serious))
    return _fake_generated_content


@pytest.fixture
def mock_generate_content_invalid(monkeypatch):
    def _raise(topic, extract, category):
        raise ValueError("JSON invalide renvoyé par le LLM")
    monkeypatch.setattr(main_content_gen, "generate_content", _raise)


@pytest.fixture
def mock_wikipedia_network_error(monkeypatch):
    def _raise(topic):
        raise ValueError("Échec réseau Wikipedia")
    monkeypatch.setattr(main_content_gen, "get_wikipedia_extract", _raise)


# --- Pipeline de génération (AC #1, #2) ---

def test_generate_creates_pending_suggestion(authenticated_client, mock_wikipedia, mock_generate_content):
    resp = authenticated_client.post("/admin/content/generate", json={"topic": "Napoléon"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "pending"
    assert body["topic"] == "Napoléon"
    assert len(body["generated_questions"]) == 2
    assert body["created_theme_id"] is None

    # Rien n'a été écrit dans Theme/Question avant approve (AC #2).
    assert authenticated_client.get("/admin/themes").json() == []
    assert authenticated_client.get("/admin/questions").json() == []


def test_generate_wikipedia_not_found_404(authenticated_client, mock_wikipedia_not_found, mock_generate_content):
    resp = authenticated_client.post("/admin/content/generate", json={"topic": "Sujetquinexistepas"})
    assert resp.status_code == 404


def test_generate_invalid_llm_response_502(authenticated_client, mock_wikipedia, mock_generate_content_invalid):
    resp = authenticated_client.post("/admin/content/generate", json={"topic": "Napoléon"})
    assert resp.status_code == 502
    # Aucune suggestion partiellement remplie n'est créée.
    assert authenticated_client.get("/admin/content/suggestions").json() == []


def test_generate_uses_explicit_category(authenticated_client, mock_wikipedia, mock_generate_content):
    resp = authenticated_client.post("/admin/content/generate", json={"topic": "Astérix", "category": "whimsical"})
    assert resp.status_code == 200
    assert resp.json()["generated_category"] == "whimsical"


def test_generate_wikipedia_network_error_502(authenticated_client, mock_wikipedia_network_error, mock_generate_content):
    # Régression : une erreur réseau/HTTP Wikipedia (pas "sujet introuvable")
    # doit être un 502 (fournisseur externe en échec), pas fuiter en 500.
    resp = authenticated_client.post("/admin/content/generate", json={"topic": "Napoléon"})
    assert resp.status_code == 502


# --- Mix de catégories (AC #3) ---

def test_category_mix_empty(authenticated_client):
    resp = authenticated_client.get("/admin/content/category-mix")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_themes"] == 0
    assert body["recommended_category"] == "serious"  # cible la plus haute (50%), en tête à égalité de vide


def test_category_mix_recommends_underrepresented_category(authenticated_client):
    authenticated_client.post("/admin/themes", json={"name": "T1", "category": "serious", "difficulty_level": 5})
    authenticated_client.post("/admin/themes", json={"name": "T2", "category": "serious", "difficulty_level": 5})
    resp = authenticated_client.get("/admin/content/category-mix")
    body = resp.json()
    assert body["total_themes"] == 2
    # 100% serious -> pop_culture et whimsical sont sous leur cible, recommandation != serious
    assert body["recommended_category"] != "serious"


# --- Validation humaine (AC #2) ---

def test_approve_suggestion_creates_theme_and_questions(authenticated_client, mock_wikipedia, mock_generate_content):
    suggestion = authenticated_client.post("/admin/content/generate", json={"topic": "Napoléon"}).json()

    resp = authenticated_client.post(f"/admin/content/suggestions/{suggestion['id']}/approve")
    assert resp.status_code == 200
    body = resp.json()
    assert body["questions_created"] == 2

    themes = authenticated_client.get("/admin/themes").json()
    assert len(themes) == 1
    assert themes[0]["name"] == "Histoire de France"

    questions = authenticated_client.get(f"/admin/questions?theme_id={themes[0]['id']}").json()
    assert len(questions) == 2


def test_approve_assigns_progressive_question_number_by_difficulty(authenticated_client, mock_wikipedia, monkeypatch):
    """La Manche 2 attend question_number 1..N croissant en difficulté
    (comme seed.py le fait à la main) : le pipeline de génération ne le
    renseignait jamais, rendant les questions générées inutilisables pour
    cette progression (bug trouvé en revue)."""
    unordered = GeneratedContent(
        theme_name="Sciences",
        category=ThemeCategoryEnum.serious,
        questions=[
            GeneratedQuestion(text="Q hard", correct_answer="A", wrong_answers=["b"], difficulty=DifficultyEnum.hard),
            GeneratedQuestion(text="Q easy", correct_answer="A", wrong_answers=["b"], difficulty=DifficultyEnum.easy),
            GeneratedQuestion(text="Q medium", correct_answer="A", wrong_answers=["b"], difficulty=DifficultyEnum.medium),
        ],
    )
    monkeypatch.setattr(main_content_gen, "generate_content", lambda topic, extract, category: unordered)

    suggestion = authenticated_client.post("/admin/content/generate", json={"topic": "Napoléon"}).json()
    authenticated_client.post(f"/admin/content/suggestions/{suggestion['id']}/approve")

    theme_id = authenticated_client.get("/admin/themes").json()[0]["id"]
    questions = authenticated_client.get(f"/admin/questions?theme_id={theme_id}").json()
    by_number = {q["question_number"]: q["difficulty"] for q in questions}
    assert by_number == {1: "easy", 2: "medium", 3: "hard"}


def test_approve_already_reviewed_suggestion_400s(authenticated_client, mock_wikipedia, mock_generate_content):
    suggestion = authenticated_client.post("/admin/content/generate", json={"topic": "Napoléon"}).json()
    authenticated_client.post(f"/admin/content/suggestions/{suggestion['id']}/approve")

    resp = authenticated_client.post(f"/admin/content/suggestions/{suggestion['id']}/approve")
    assert resp.status_code == 400


def test_approve_logs_question_creations_not_false_theme_creation_on_reuse(authenticated_client, mock_wikipedia, mock_generate_content):
    # Régression : réutiliser un thème existant ne doit PAS logger un faux
    # "theme created" ; les questions créées DOIVENT être loggées (AC #5).
    authenticated_client.post("/admin/themes", json={"name": "Histoire de France", "category": "serious", "difficulty_level": 5})
    suggestion = authenticated_client.post("/admin/content/generate", json={"topic": "Napoléon"}).json()
    authenticated_client.post(f"/admin/content/suggestions/{suggestion['id']}/approve")

    theme = next(t for t in authenticated_client.get("/admin/themes").json() if t["name"] == "Histoire de France")
    theme_history = authenticated_client.get(f"/admin/content/history?entity_type=theme&entity_id={theme['id']}").json()
    # Un seul "created" (F.1, avant la génération) — pas un second via l'approve.
    assert len([h for h in theme_history if h["action"] == "created"]) == 1

    question_history = authenticated_client.get("/admin/content/history?entity_type=question").json()
    assert len(question_history) == 2  # les 2 questions générées, chacune loggée


def test_reject_suggestion_does_not_create_content(authenticated_client, mock_wikipedia, mock_generate_content):
    suggestion = authenticated_client.post("/admin/content/generate", json={"topic": "Napoléon"}).json()

    resp = authenticated_client.post(f"/admin/content/suggestions/{suggestion['id']}/reject", json={"reason": "Erreurs factuelles"})
    assert resp.status_code == 200

    assert authenticated_client.get("/admin/themes").json() == []
    updated = authenticated_client.get("/admin/content/suggestions?status=rejected").json()
    assert len(updated) == 1
    assert updated[0]["rejection_reason"] == "Erreurs factuelles"


def test_approve_reuses_existing_theme_by_name(authenticated_client, mock_wikipedia, mock_generate_content):
    authenticated_client.post("/admin/themes", json={"name": "Histoire de France", "category": "serious", "difficulty_level": 5})
    suggestion = authenticated_client.post("/admin/content/generate", json={"topic": "Napoléon"}).json()
    authenticated_client.post(f"/admin/content/suggestions/{suggestion['id']}/approve")

    themes = authenticated_client.get("/admin/themes").json()
    assert len(themes) == 1  # pas de doublon de thème


def test_list_suggestions_filtered_by_status(authenticated_client, mock_wikipedia, mock_generate_content):
    s1 = authenticated_client.post("/admin/content/generate", json={"topic": "A"}).json()
    authenticated_client.post("/admin/content/generate", json={"topic": "B"})
    authenticated_client.post(f"/admin/content/suggestions/{s1['id']}/approve")

    pending = authenticated_client.get("/admin/content/suggestions?status=pending").json()
    approved = authenticated_client.get("/admin/content/suggestions?status=approved").json()
    assert len(pending) == 1
    assert len(approved) == 1


# --- Signalement joueur (AC #4) ---

def test_flag_question(authenticated_client):
    question = authenticated_client.post("/admin/questions", json={
        "text": "Q", "category": "cat", "difficulty": "easy", "points": 2,
        "correct_answer": "A", "wrong_answers": ["B", "C", "D"],
    }).json()

    resp = authenticated_client.post(f"/questions/{question['id']}/flag", json={"reason": "Réponse incorrecte"})
    assert resp.status_code == 200

    flags = authenticated_client.get("/admin/content/flags?resolved=false").json()
    assert len(flags) == 1
    assert flags[0]["reason"] == "Réponse incorrecte"


def test_flag_unknown_question_404s(authenticated_client):
    resp = authenticated_client.post("/questions/999999/flag", json={"reason": "x"})
    assert resp.status_code == 404


def test_resolve_flag(authenticated_client):
    question = authenticated_client.post("/admin/questions", json={
        "text": "Q", "category": "cat", "difficulty": "easy", "points": 2,
        "correct_answer": "A", "wrong_answers": ["B", "C", "D"],
    }).json()
    flag = authenticated_client.post(f"/questions/{question['id']}/flag", json={"reason": "x"}).json()

    resp = authenticated_client.post(f"/admin/content/flags/{flag['flag_id']}/resolve", json={"note": "Corrigé"})
    assert resp.status_code == 200
    assert resp.json()["resolved"] is True

    unresolved = authenticated_client.get("/admin/content/flags?resolved=false").json()
    assert unresolved == []


# --- Historique (AC #5) ---

def test_history_logs_f1_theme_create(authenticated_client):
    authenticated_client.post("/admin/themes", json={"name": "T", "category": "serious", "difficulty_level": 5})
    history = authenticated_client.get("/admin/content/history?entity_type=theme").json()
    assert any(h["action"] == "created" for h in history)


def test_history_logs_f1_theme_delete(authenticated_client):
    theme = authenticated_client.post("/admin/themes", json={"name": "T", "category": "serious", "difficulty_level": 5}).json()
    authenticated_client.delete(f"/admin/themes/{theme['id']}")
    history = authenticated_client.get(f"/admin/content/history?entity_type=theme&entity_id={theme['id']}").json()
    actions = [h["action"] for h in history]
    assert "created" in actions and "deleted" in actions


def test_history_logs_generation_and_approval(authenticated_client, mock_wikipedia, mock_generate_content):
    suggestion = authenticated_client.post("/admin/content/generate", json={"topic": "Napoléon"}).json()
    authenticated_client.post(f"/admin/content/suggestions/{suggestion['id']}/approve")

    history = authenticated_client.get(f"/admin/content/history?entity_type=suggestion&entity_id={suggestion['id']}").json()
    actions = [h["action"] for h in history]
    assert "generated" in actions
    assert "approved" in actions


def test_history_logs_flag_and_resolve(authenticated_client):
    question = authenticated_client.post("/admin/questions", json={
        "text": "Q", "category": "cat", "difficulty": "easy", "points": 2,
        "correct_answer": "A", "wrong_answers": ["B", "C", "D"],
    }).json()
    flag = authenticated_client.post(f"/questions/{question['id']}/flag", json={"reason": "x"}).json()
    authenticated_client.post(f"/admin/content/flags/{flag['flag_id']}/resolve", json={"note": "ok"})

    history = authenticated_client.get(f"/admin/content/history?entity_type=flag&entity_id={flag['flag_id']}").json()
    actions = [h["action"] for h in history]
    assert "flagged" in actions and "resolved" in actions


def test_history_respects_limit(authenticated_client):
    for i in range(5):
        authenticated_client.post("/admin/themes", json={"name": f"T{i}", "category": "serious", "difficulty_level": 5})
    history = authenticated_client.get("/admin/content/history?limit=2").json()
    assert len(history) == 2


# --- Tests unitaires directs (contournent le mock au niveau du router,
# exercent réellement le parsing/l'encodage — trouvé en revue de code : les
# fixtures ci-dessus mockent la frontière du router et ne prouvent jamais que
# wikipedia_client.py / content_generator.py fonctionnent réellement) ---

class TestWikipediaClientUnit:
    def test_topic_is_url_encoded(self, monkeypatch):
        import httpx
        from app import wikipedia_client

        captured_url = {}

        def fake_get(url, timeout=None, headers=None):
            captured_url["url"] = url
            request = httpx.Request("GET", url)
            return httpx.Response(200, json={"extract": "ok"}, request=request)

        monkeypatch.setattr(httpx, "get", fake_get)
        wikipedia_client.get_wikipedia_extract("AC/DC")
        assert "AC%2FDC" in captured_url["url"]
        assert captured_url["url"].count("/summary/") == 1

    def test_404_raises_lookup_error(self, monkeypatch):
        import httpx
        from app import wikipedia_client

        def fake_get(url, timeout=None, headers=None):
            request = httpx.Request("GET", url)
            return httpx.Response(404, request=request)

        monkeypatch.setattr(httpx, "get", fake_get)
        with pytest.raises(LookupError):
            wikipedia_client.get_wikipedia_extract("Sujetquinexistepas")

    def test_network_error_raises_value_error(self, monkeypatch):
        import httpx
        from app import wikipedia_client

        def fake_get(url, timeout=None, headers=None):
            raise httpx.ConnectError("refused")

        monkeypatch.setattr(httpx, "get", fake_get)
        with pytest.raises(ValueError):
            wikipedia_client.get_wikipedia_extract("Napoléon")

    def test_server_error_raises_value_error(self, monkeypatch):
        import httpx
        from app import wikipedia_client

        def fake_get(url, timeout=None, headers=None):
            request = httpx.Request("GET", url)
            return httpx.Response(503, request=request)

        monkeypatch.setattr(httpx, "get", fake_get)
        with pytest.raises(ValueError):
            wikipedia_client.get_wikipedia_extract("Napoléon")


class TestContentGeneratorUnit:
    def test_api_error_raises_value_error(self, monkeypatch):
        import anthropic
        from app import content_generator

        class FakeMessages:
            def create(self, **kwargs):
                raise anthropic.APIConnectionError(request=None)

        class FakeClient:
            messages = FakeMessages()

        monkeypatch.setattr(content_generator, "_get_client", lambda: FakeClient())
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

        with pytest.raises(ValueError):
            content_generator.generate_content("Napoléon", "extrait", None)

    def test_invalid_json_raises_value_error(self, monkeypatch):
        from app import content_generator

        class FakeBlock:
            type = "text"
            text = "ceci n'est pas du JSON"

        class FakeResponse:
            content = [FakeBlock()]

        class FakeMessages:
            def create(self, **kwargs):
                return FakeResponse()

        class FakeClient:
            messages = FakeMessages()

        monkeypatch.setattr(content_generator, "_get_client", lambda: FakeClient())

        with pytest.raises(ValueError):
            content_generator.generate_content("Napoléon", "extrait", None)

    def test_missing_api_key_raises_runtime_error(self, monkeypatch):
        from app import content_generator

        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        with pytest.raises(RuntimeError):
            content_generator.generate_content("Napoléon", "extrait", None)
