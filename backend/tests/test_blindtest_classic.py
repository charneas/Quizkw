"""Barème et reconnaissance des réponses du blind test classique : matrice I/O
de spec-blindtest-classique.md."""
import importlib.util
from pathlib import Path

import pytest

from main_blindtest import MIN_CLASSIC_ROUNDS
from app.blindtest import presets
from app.blindtest.classic import ARTIST, TITLE, build_reference, match_answer, points
from app.blindtest.song_identity import SongTrack, group_songs


def _load_snapshot_script():
    path = Path(__file__).resolve().parents[1] / "scripts" / "snapshot_blindtest_presets.py"
    spec = importlib.util.spec_from_file_location("snapshot_blindtest_presets", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestPoints:
    @pytest.mark.parametrize(
        "found_title, found_artist, elapsed, expected",
        [
            (True, False, 10, 60),
            (True, True, 0, 200),
            (True, False, 0, 100),
            (False, True, 0, 60),
            (True, False, 20, 20),
            (False, True, 20, 12),
            (True, True, 20, 40),
            (False, False, 3, 0),
        ],
    )
    def test_curve(self, found_title, found_artist, elapsed, expected):
        assert points(found_title, found_artist, elapsed) == expected

    def test_each_element_is_timed_separately(self):
        # Titre à 0 s (100) et artiste à 20 s (12), plus 25 % de la somme.
        assert points(True, True, (0, 20)) == 140

    def test_decay_is_continuous(self):
        values = [points(True, False, tenth / 10) for tenth in range(0, 201)]
        assert all(a >= b for a, b in zip(values, values[1:]))
        assert all(a - b <= 1 for a, b in zip(values, values[1:]))

    def test_elapsed_outside_the_round_is_clamped(self):
        assert points(True, False, -5) == 100
        assert points(True, False, 25) == 20

    def test_second_find_never_lowers_the_score(self):
        for title_elapsed in range(0, 21):
            for artist_elapsed in range(title_elapsed, 21):
                alone = points(True, False, (title_elapsed, 0))
                assert points(True, True, (title_elapsed, artist_elapsed)) > alone

    def test_score_is_an_integer(self):
        assert isinstance(points(True, True, (3.3, 7.7)), int)


class TestBuildReference:
    def test_strips_version_noise(self):
        ref = build_reference("One More Time (Remastered 2011)", "Daft Punk")
        assert ref.title == "One More Time"
        assert ref.artist == "Daft Punk"

    @pytest.mark.parametrize("noise", ["(Clip officiel)", "(Official HD Video)", "[4K]", "(Official Video)"])
    def test_strips_youtube_suffixes(self, noise):
        assert build_reference(f"Song Name {noise}", "Artist").title == "Song Name"

    def test_artist_prefix_wins_over_compilation_channel(self):
        ref = build_reference("Daft Punk - One More Time (Clip officiel)", "Best Hits Compilation")
        assert ref.title == "One More Time"
        assert ref.artist == "Daft Punk"

    def test_vevo_channel(self):
        ref = build_reference("Stromae - Alors on danse (Clip officiel)", "StromaeVEVO")
        assert ref.title == "Alors on danse"
        assert ref.artist == "Stromae"

    def test_title_then_artist_when_channel_names_the_second_part(self):
        ref = build_reference("One More Time - Daft Punk", "Daft Punk")
        assert ref.title == "One More Time"
        assert ref.artist == "Daft Punk"

    def test_quoted_title_first(self):
        ref = build_reference('"Una Lluna" - Miki', "Operacion Triunfo")
        assert ref.title == "Una Lluna"
        assert ref.artist == "Miki"

    def test_archive_format(self):
        ref = build_reference('Joe Dassin "Les Champs-Elysees" | Archive INA', "Ina Chansons")
        assert ref.title == "Les Champs-Elysees"
        assert ref.artist == "Joe Dassin"

    def test_topic_channel_bare_title(self):
        ref = build_reference("Alors on danse", "Stromae")
        assert ref.title == "Alors on danse"
        assert ref.artist == "Stromae"

    def test_colon_is_not_an_artist_separator(self):
        assert build_reference("Star Wars : Main Theme", "John Williams").artist == "John Williams"

    def test_structured_fields_are_not_split_on_a_dash(self):
        ref = build_reference("Shallow - From A Star Is Born", "Lady Gaga", structured=True)
        assert ref.title == "Shallow"
        assert ref.artist == "Lady Gaga"

    @pytest.mark.parametrize("version", ["From A Star Is Born", "Live in Paris", "Remastered Edition", "Radio Edit Mix"])
    def test_version_after_dash_keeps_the_channel_as_artist(self, version):
        ref = build_reference(f"Shallow - {version}", "Lady Gaga")
        assert ref.title == "Shallow"
        assert ref.artist == "Lady Gaga"

    def test_title_starting_like_a_version_stays_a_title(self):
        ref = build_reference("Beatles - From Me to You", "The Beatles")
        assert ref.title == "From Me to You"
        assert ref.artist == "Beatles"

    def test_live_forever_is_a_title(self):
        ref = build_reference("Oasis - Live Forever", "Hits Compilation")
        assert ref.title == "Live Forever"
        assert ref.artist == "Oasis"

    def test_em_dash_is_a_separator(self):
        ref = build_reference("Song — Some Artist", "Some Artist")
        assert ref.title == "Song"
        assert ref.artist == "Some Artist"

    def test_feat_is_removed_from_title_and_artist(self):
        ref = build_reference("Levitating (feat. DaBaby)", "Dua Lipa feat. DaBaby")
        assert ref.title == "Levitating"
        assert ref.artist == "Dua Lipa"


class TestMatchAnswer:
    @pytest.mark.parametrize(
        "answer, title, artist, expected",
        [
            ("beyonce", "Halo", "Beyoncé", {ARTIST}),
            ("Daft Ponk", "One More Time", "Daft Punk", {ARTIST}),
            ("one more time", "One More Time (Remastered 2011)", "Daft Punk", {TITLE}),
            ("dua lipa", "Levitating", "Dua Lipa feat. DaBaby", {ARTIST}),
            ("Sea", "Chandelier", "Sia", set()),
            ("sia", "Chandelier", "Sia", {ARTIST}),
            ("bohemian", "Bohemian Rhapsody", "Queen", set()),
            ("daft punk one more time", "One More Time", "Daft Punk", {TITLE, ARTIST}),
            ("one more time daft punk", "One More Time", "Daft Punk", {TITLE, ARTIST}),
            ("killer queen", "Killer Queen", "Queen", {TITLE}),
            ("", "One More Time", "Daft Punk", set()),
            ("???", "One More Time", "Daft Punk", set()),
        ],
    )
    def test_matrix(self, answer, title, artist, expected):
        assert match_answer(answer, build_reference(title, artist)) == expected

    def test_co_artists_are_accepted_individually(self):
        ref = build_reference("Song Title", "Simon & Garfunkel")
        assert match_answer("garfunkel", ref) == {ARTIST}
        assert match_answer("simon and garfunkel", ref) == {ARTIST}

    def test_leading_the_is_optional(self):
        ref = build_reference("Roxanne", "The Police")
        assert match_answer("police", ref) == {ARTIST}
        assert match_answer("the police", ref) == {ARTIST}

    def test_short_reference_is_found_inside_a_sentence(self):
        assert match_answer("je dirais sia", build_reference("Chandelier", "Sia")) == {ARTIST}

    def test_eponymous_song_scores_both_with_the_same_word(self):
        ref = build_reference("Weezer", "Weezer")
        first = match_answer("weezer", ref)
        assert len(first) == 1
        assert match_answer("weezer", ref, skip=first) == {TITLE, ARTIST} - first

    def test_retyping_a_found_title_does_not_give_the_artist_inside_it(self):
        ref = build_reference("Killer Queen", "Queen")
        assert match_answer("killer queen", ref) == {TITLE}
        assert match_answer("killer queen", ref, skip={TITLE}) == set()
        assert match_answer("queen", ref, skip={TITLE}) == {ARTIST}
        assert match_answer("killer queen queen", ref, skip={TITLE}) == {ARTIST}

    def test_skip_ignores_already_found_elements(self):
        ref = build_reference("One More Time", "Daft Punk")
        assert match_answer("daft punk one more time", ref, skip={TITLE}) == {ARTIST}

    def test_subtitle_is_optional(self):
        ref = build_reference("Don't Stop (Thinking About Tomorrow)", "Fleetwood Mac")
        assert match_answer("dont stop", ref) == {TITLE}
        assert match_answer("don't stop thinking about tomorrow", ref) == {TITLE}


@pytest.mark.parametrize("preset", presets.PRESETS, ids=lambda preset: preset.slug)
class TestRealPresets:
    def test_tracks_are_complete(self, preset):
        tracks = presets.load_tracks(preset)
        for track in tracks:
            assert track["youtube_video_id"] and track["title"] and track["artist"]
            assert track["duration_seconds"] > 0

    def test_enough_distinct_songs(self, preset):
        songs = group_songs(
            SongTrack(
                id=index,
                title=track["title"],
                artist=track["artist"],
                youtube_video_id=track["youtube_video_id"],
                duration_seconds=track["duration_seconds"],
            )
            for index, track in enumerate(presets.load_tracks(preset))
        )
        assert len(set(songs.values())) >= MIN_CLASSIC_ROUNDS

    def test_every_answer_can_be_found(self, preset):
        for track in presets.load_tracks(preset):
            reference = build_reference(track["title"], track["artist"], structured=True)
            assert reference.titles, track
            assert reference.artists, track


class TestSnapshotFilter:
    def _details(self, **overrides):
        return {
            "contentDetails": {"duration": "PT3M20S"},
            "status": {"embeddable": True, "privacyStatus": "public"},
            **overrides,
        }

    def test_keeps_embeddable_video_with_its_duration(self):
        assert _load_snapshot_script().playable_duration(self._details()) == 200

    def test_rejects_unplayable_videos(self):
        script = _load_snapshot_script()
        assert script.playable_duration(self._details(status={"embeddable": False, "privacyStatus": "public"})) is None
        assert script.playable_duration(self._details(status={"embeddable": True, "privacyStatus": "private"})) is None
        assert script.playable_duration(self._details(contentDetails={"duration": "P0D"})) is None
        assert script.playable_duration(
            self._details(contentDetails={"duration": "PT3M", "regionRestriction": {"blocked": ["FR"]}})
        ) is None
