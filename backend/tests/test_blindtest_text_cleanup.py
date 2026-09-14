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

    def test_strips_vevo_suffix_and_splits_camel_case(self):
        title, artist = clean_title_artist("begged", "OliviaRodrigoVEVO")
        assert artist == "Olivia Rodrigo"
        assert title == "begged"

    def test_vevo_stripped_without_mangling_names_that_already_have_spaces(self):
        _, artist = clean_title_artist("Song", "Katy Perry VEVO")
        assert artist == "Katy Perry"

    def test_strips_redundant_artist_prefix_once_artist_is_cleaned(self):
        title, artist = clean_title_artist(
            "Olivia Rodrigo - begged (Saturday Night Live 2026)", "OliviaRodrigoVEVO"
        )
        assert artist == "Olivia Rodrigo"
        assert title == "begged (Saturday Night Live 2026)"

    def test_does_not_strip_prefix_that_does_not_match_artist(self):
        title, artist = clean_title_artist("Something - Not the artist", "Real Artist")
        assert title == "Something - Not the artist"
        assert artist == "Real Artist"

    def test_truncates_title_at_first_pipe_broadcast_context(self):
        title, artist = clean_title_artist(
            "Barbara Pravi - Voilà (LIVE) | France 🇫🇷 | Grand Final | Eurovision 2021",
            "Eurovision Song Contest",
        )
        assert title == "Barbara Pravi - Voilà (LIVE)"
        assert artist == "Eurovision Song Contest"
