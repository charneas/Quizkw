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

    def test_broadcast_title_uses_real_performer_instead_of_channel_name(self):
        # Retour utilisateur (2026-09-15) : "Eurovision Song Contest donne
        # beaucoup trop de contexte à la chanson" — sur un titre de
        # diffusion, le champ `artist` d'origine est le nom de la chaîne/de
        # l'émission, jamais le vrai artiste ; celui-ci (et le titre sans son
        # préfixe) sont extraits du titre "{Artiste} - {Titre}" à la place.
        title, artist = clean_title_artist(
            "FAHREE feat. Ilkin Dovlatov - Özünlə Apar | Azerbaijan 🇦🇿 "
            "| Showcase Performance | Eurovision 2024",
            "Eurovision Song Contest",
        )
        assert title == "Özünlə Apar"
        assert artist == "FAHREE feat. Ilkin Dovlatov"

    def test_broadcast_title_still_truncates_pipe_context(self):
        title, artist = clean_title_artist(
            "Barbara Pravi - Voilà (LIVE) | France 🇫🇷 | Grand Final | Eurovision 2021",
            "Eurovision Song Contest",
        )
        assert title == "Voilà (LIVE)"
        assert artist == "Barbara Pravi"

    def test_never_truncates_pipe_without_a_broadcast_marker(self):
        # Retour utilisateur (2026-09-15, données réelles en réconciliation) :
        # un "|" n'est pas toujours un séparateur de contexte de diffusion —
        # ici le vrai titre/artiste est justement APRÈS le premier "|". Sans
        # marqueur fort (drapeau/mot-clé Eurovision), ne jamais tronquer.
        title, artist = clean_title_artist(
            "DORA 2026 | LELEK - ANDROMEDA | POBJEDNIČKI NASTUP", "Dora | HRT"
        )
        assert title == "DORA 2026 | LELEK - ANDROMEDA | POBJEDNIČKI NASTUP"
        assert artist == "Dora | HRT"

    def test_truncates_pipe_and_extracts_artist_when_keyword_not_in_first_segment(self):
        title, artist = clean_title_artist(
            "NAPA - Deslocado | 2ª Semifinal | Festival da Canção 2025", "Festival da Canção"
        )
        assert title == "Deslocado"
        assert artist == "NAPA"
