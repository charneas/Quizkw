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

    def test_never_truncates_pipe_when_first_segment_has_no_artist_song_split(self):
        # Retour utilisateur (2026-09-15, données réelles en réconciliation) :
        # un "|" n'est pas toujours un séparateur de contexte de diffusion —
        # ici le vrai titre/artiste est justement APRÈS le premier "|". Le
        # signal de confiance est structurel (la portion avant le "|"
        # ressemble-t-elle à "Artiste - Titre" ?), pas un mot-clé : "DORA
        # 2026" n'a pas de séparateur -> on ne devine rien.
        title, artist = clean_title_artist(
            "DORA 2026 | LELEK - ANDROMEDA | POBJEDNIČKI NASTUP", "Dora | HRT"
        )
        assert title == "DORA 2026 | LELEK - ANDROMEDA | POBJEDNIČKI NASTUP"
        assert artist == "Dora | HRT"

    def test_extracts_artist_from_any_broadcaster_not_just_eurovision(self):
        # Retour utilisateur (2026-09-15) : "faut faire attention que
        # l'artiste/nom de la chanson sont cohérents [...] Si si faut
        # toucher" — Festival da Canção (sélection portugaise) suit la même
        # convention "Artiste - Titre | contexte de diffusion" qu'Eurovision
        # Song Contest ; le signal structurel (dash dans la portion avant le
        # "|") s'applique à n'importe quel diffuseur, pas seulement Eurovision.
        title, artist = clean_title_artist(
            "NAPA - Deslocado | 2ª Semifinal | Festival da Canção 2025", "Festival da Canção"
        )
        assert title == "Deslocado"
        assert artist == "NAPA"

    def test_extracts_artist_across_en_dash_separator(self):
        # Retour utilisateur (2026-09-15, données réelles) : certains titres
        # Eurovision utilisent un tiret demi-cadratin "–" au lieu d'un
        # hyphen normal comme séparateur artiste/titre.
        title, artist = clean_title_artist(
            "Sissal – Hallucination (LIVE) | Denmark 🇩🇰 | Grand Final | Eurovision 2025",
            "Eurovision Song Contest",
        )
        assert title == "Hallucination (LIVE)"
        assert artist == "Sissal"

    def test_never_touches_unrelated_titles_with_a_flag_emoji_or_final_keyword(self):
        title, artist = clean_title_artist(
            "Some Random Sports Final | Team A vs Team B 🇫🇷", "Some Channel"
        )
        assert title == "Some Random Sports Final | Team A vs Team B 🇫🇷"
        assert artist == "Some Channel"

    def test_never_touches_broadcast_titles_without_a_pipe(self):
        # Retour utilisateur (2026-09-15, revue après un bug trouvé en
        # dry-run) : un repli sur le mot "Eurovision" pour un titre SANS "|"
        # avait été tenté puis abandonné — rejouer le script sur un titre
        # déjà nettoyé une première fois pouvait re-déclencher un second
        # découpage à tort sur ce qui restait (non idempotent, destructif sur
        # relance). Sans "|", on ne devine plus rien : le champ `artist`
        # d'origine reste tel quel, même imparfait.
        title, artist = clean_title_artist(
            "Hovig - Gravity (Cyprus) Eurovision 2017 - Official Music Video",
            "Eurovision Song Contest",
        )
        assert title == "Hovig - Gravity (Cyprus) Eurovision 2017 - Official Music Video"
        assert artist == "Eurovision Song Contest"

    def test_unquoted_artist_followed_by_quoted_title_no_dash(self):
        # Retour utilisateur (2026-09-15) : "Serge Lama 'Je suis malade' |
        # INA Chansons c'est juste la chanson Je suis malade de Serge Lama"
        # — troisième convention, sans tiret du tout : l'artiste précède
        # directement le titre entre guillemets.
        title, artist = clean_title_artist(
            'Serge Lama "Je suis malade" | INA Chansons', "INA Chansons"
        )
        assert title == "Je suis malade"
        assert artist == "Serge Lama"

    def test_reaction_video_description_is_not_mistaken_for_an_artist(self):
        # Retour utilisateur (2026-09-15, trouvé en dry-run avant application
        # prod) : la convention "Artiste \"Titre\"" sans tiret matche aussi
        # des titres de vidéo de réaction sans rapport ("First Time Reacting
        # to ADO" n'est pas un nom d'artiste) — trop de mots + mot-clé
        # "reacting" -> pas assez plausible comme artiste, on ne touche rien.
        title, artist = clean_title_artist(
            'First Time Reacting to ADO "RuLe" | REACTION!', "G.O.T Games"
        )
        assert title == 'First Time Reacting to ADO "RuLe" | REACTION!'
        assert artist == "G.O.T Games"

    def test_reversed_quoted_title_convention_is_not_flipped_backwards(self):
        # Retour utilisateur (2026-09-15, trouvé en dry-run) : "Operación
        # Triunfo" (émission TV espagnole) inverse la convention —
        # '"Titre" - Interprète' au lieu de "Artiste - Titre". Sans le
        # garde-fou sur les guillemets, le titre entre guillemets (la vraie
        # chanson) finissait pris pour l'artiste, et l'interprète pour le
        # titre — exactement inversé.
        title, artist = clean_title_artist(
            "“UNA LLUNA A L’AIGUA” - MIKI | GALA 9 | OT 2018", "Operación Triunfo Oficial"
        )
        assert title == "UNA LLUNA A L’AIGUA"
        assert artist == "MIKI"

    def test_reversed_quoted_title_convention_with_two_performers(self):
        title, artist = clean_title_artist(
            "“NADIE SE SALVA” - NATALIA y MIKI | Gala Eurovisión 2019 | OT 2018",
            "Operación Triunfo Oficial",
        )
        assert title == "NADIE SE SALVA"
        assert artist == "NATALIA y MIKI"

    def test_straight_quotes_also_trigger_reversed_convention(self):
        title, artist = clean_title_artist(
            '"El Ataque" - Carlos y Miki | Gala 1 | OT 2018', "Operación Triunfo Oficial"
        )
        assert title == "El Ataque"
        assert artist == "Carlos y Miki"

    def test_extraction_is_idempotent_on_already_cleaned_multi_dash_title(self):
        # Régression du bug trouvé en dry-run (2026-09-15) : un titre déjà
        # nettoyé une première fois ("Bella - LIVE at ... - Eurovision 2026",
        # lui-même un reliquat légitime contenant plusieurs tirets et le mot
        # "Eurovision") ne doit PAS être re-découpé à la relance du script.
        first_pass_title, first_pass_artist = clean_title_artist(
            "AIDAN - Bella - LIVE at EUROVIZIJA.LT 2026 - Lithuanian National "
            "Final - Malta - Eurovision 2026 🇲🇹",
            "AIDAN",
        )
        assert first_pass_artist == "AIDAN"
        second_pass_title, second_pass_artist = clean_title_artist(
            first_pass_title, first_pass_artist
        )
        assert (second_pass_title, second_pass_artist) == (first_pass_title, first_pass_artist)
