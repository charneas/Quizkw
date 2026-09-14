"""Retour utilisateur (2026-09-14) : "réconciliation des chansons et
uniformisation dans la base de données" — tests du nettoyage non destructif
de `app/blindtest/text_cleanup.py`."""
from app.blindtest.text_cleanup import clean_title_artist


class TestCleanTitleArtist:
    def test_strips_trailing_official_video_suffix(self):
        title, artist = clean_title_artist("Get Lucky (Official Music Video)", "Daft Punk")
        assert title == "Get Lucky"
        assert artist == "Daft Punk"

    def test_strips_trailing_lyrics_suffix_case_insensitive(self):
        title, _ = clean_title_artist("Some Song [OFFICIAL LYRIC VIDEO]", "Someone")
        assert title == "Some Song"

    def test_decodes_html_entities(self):
        title, _ = clean_title_artist("Bonnie &amp; Clyde", "Someone")
        assert title == "Bonnie & Clyde"

    def test_collapses_extra_whitespace(self):
        title, artist = clean_title_artist("Get   Lucky  ", "  Daft   Punk")
        assert title == "Get Lucky"
        assert artist == "Daft Punk"

    def test_never_touches_legitimate_parentheses(self):
        # Ne doit jamais retirer une parenthèse qui fait partie du titre
        # réel — seuls les suffixes techniques connus sont ciblés.
        title, _ = clean_title_artist("Weird (Parentheses) Title", "Artist")
        assert title == "Weird (Parentheses) Title"

    def test_never_forces_case_or_strips_intentional_accents(self):
        title, artist = clean_title_artist("Sväfn-g-englar", "Sigur Rós")
        assert title == "Sväfn-g-englar"
        assert artist == "Sigur Rós"

    def test_empty_strings_are_returned_unchanged(self):
        assert clean_title_artist("", "") == ("", "")
