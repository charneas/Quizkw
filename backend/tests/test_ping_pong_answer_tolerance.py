"""
Tolérance aux fautes de frappe dans les réponses ping-pong (BUG-504, #36).

Tests unitaires purs sur answer_matches_with_tolerance : pas besoin de DB,
la logique de tolérance est indépendante du reste du manager.
"""
from app.ping_pong_manager import answer_matches_with_tolerance


def test_exact_match_accepted():
    assert answer_matches_with_tolerance("paris", ["paris"]) is True


def test_one_letter_typo_accepted_above_threshold():
    # "paris" (5) vs "paros" : substitution unique
    assert answer_matches_with_tolerance("paros", ["paris"]) is True
    # lettre manquante
    assert answer_matches_with_tolerance("pari", ["paris"]) is True
    # lettre en trop
    assert answer_matches_with_tolerance("parris", ["paris"]) is True


def test_two_letter_typo_rejected():
    assert answer_matches_with_tolerance("parxx", ["paris"]) is False


def test_short_answer_requires_exact_match():
    # "roi" / "toi" : distance 1 mais réponse <= 3 caractères, pas de tolérance
    assert answer_matches_with_tolerance("toi", ["roi"]) is False
    assert answer_matches_with_tolerance("roi", ["roi"]) is True


def test_typo_matches_against_any_accepted_answer():
    assert answer_matches_with_tolerance("londre", ["paris", "londres"]) is True


def test_completely_wrong_answer_rejected():
    assert answer_matches_with_tolerance("berlin", ["paris"]) is False