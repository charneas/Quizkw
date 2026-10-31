"""Reconnaissance d'une même chanson entre playlists (`song_identity`).

Les faux positifs comptent autant que les faux négatifs : taguer à tort un
joueur lui donne des points indus, d'où les deux corpus `SAME` et `DIFFERENT`."""
import random
import time

import pytest

from app.blindtest.song_identity import SongTrack, group_songs


def deezer(title, artist, **kwargs):
    return dict(title=title, artist=artist, structured=True, **kwargs)


def youtube(title, channel, **kwargs):
    return dict(title=title, artist=channel, structured=False, **kwargs)


def same_song(a, b):
    songs = group_songs([SongTrack(id=1, **a), SongTrack(id=2, **b)])
    return songs[1] == songs[2]


SAME = [
    # Deezer contre titre de vidéo YouTube
    (deezer("Get Lucky (feat. Pharrell Williams)", "Daft Punk"), youtube("Daft Punk - Get Lucky (Official Audio)", "SomeChannel")),
    (deezer("Get Lucky", "Daft Punk"), youtube("Get Lucky - Daft Punk", "SomeChannel")),
    (deezer("Get Lucky", "Daft Punk"), youtube("Daft Punk Get Lucky lyrics", "SomeChannel")),
    (deezer("Get Lucky", "Daft Punk"), youtube("Get Lucky by Daft Punk", "SomeChannel")),
    (deezer("Get Lucky", "Daft Punk"), youtube('Daft Punk "Get Lucky"', "SomeChannel")),
    (deezer("Get Lucky", "Daft Punk"), youtube("DAFT PUNK | GET LUCKY | HD", "SomeChannel")),
    (deezer("Get Lucky", "Daft Punk"), youtube("Daft Punk - Get Lucky - Official Video", "Daft Punk")),
    (deezer("Get Lucky", "Daft Punk"), youtube("Get Lucky ft. Pharrell Williams", "DaftPunkOfficial")),
    (deezer("Stay", "Zedd"), youtube("Zedd, Alessia Cara - Stay (Official Video)", "Zedd")),
    (deezer("Alors on danse", "Stromae"), youtube("Stromae - Alors on danse (Clip Officiel)", "Stromae")),
    (deezer("Alors on danse", "Stromae"), youtube("Stromae : Alors on danse [paroles]", "lyrics fr")),
    # Mots de version qui font partie du vrai titre
    (deezer("Radio Ga Ga", "Queen"), youtube("Queen - Radio Ga Ga", "SomeChannel")),
    (deezer("Stereo Hearts", "Gym Class Heroes"), youtube("Gym Class Heroes - Stereo Hearts", "SomeChannel")),
    (deezer("Live and Let Die", "Wings"), youtube("Wings - Live and Let Die", "SomeChannel")),
    (deezer("Single Ladies", "Beyoncé"), youtube("Beyoncé - Single Ladies (Official Video)", "SomeChannel")),
    (deezer("Radio", "Rammstein"), youtube("Rammstein - Radio", "SomeChannel")),
    (deezer("From Me to You", "The Beatles"), youtube("The Beatles - From Me to You", "SomeChannel")),
    # Deux vidéos YouTube de chaînes différentes
    (youtube("Daft Punk - Get Lucky", "ChannelA"), youtube("Get Lucky - Daft Punk (Lyrics)", "ChannelB")),
    (youtube("Daft Punk Get Lucky", "ChannelA"), youtube("Get Lucky Daft Punk", "ChannelB")),
    # Orthographe
    (deezer("Don't Stop Believin'", "Journey"), deezer("Don’t Stop Believing", "Journey")),
    (deezer("Dont Stop Believin", "Journey"), deezer("Don't Stop Believing", "Journey")),
    (deezer("Thunderstruck", "AC/DC"), deezer("Thunderstruck", "ACDC")),
    (deezer("Thunderstruck", "AC/DC"), deezer("Thunderstruck", "AC-DC")),
    (deezer("Yesterday", "The Beatles"), deezer("Yesterday", "Beatles")),
    (deezer("Try", "P!nk"), deezer("Try", "Pink")),
    (deezer("TiK ToK", "Ke$ha"), deezer("Tik Tok", "Kesha")),
    (deezer("Losing My Religion", "R.E.M."), deezer("Losing My Religion", "REM")),
    (deezer("Crazy in Love", "Beyoncé"), deezer("Crazy In Love", "Beyonce")),
    (deezer("Rock & Roll", "Led Zeppelin"), deezer("Rock and Roll", "Led Zeppelin")),
    (deezer("Rock 'n' Roll", "Led Zeppelin"), deezer("Rock and Roll", "Led Zeppelin")),
    (deezer("Anti-Hero", "Taylor Swift"), deezer("Antihero", "Taylor Swift")),
    (deezer("Another Brick in the Wall, Pt. 2", "Pink Floyd"), deezer("Another Brick In The Wall (Part II)", "Pink Floyd")),
    (deezer("Cœur de pirate", "Artiste"), deezer("Coeur de Pirate", "Artiste")),
    (deezer("Mr. Brightside", "The Killers"), deezer("Mr Brightside", "Killers")),
    (deezer("L'Aziza", "Daniel Balavoine"), deezer("L’aziza", "Balavoine")),
    (deezer("Toi et moi", "Grégoire"), deezer("Toi & moi", "Gregoire")),
    # Artistes multiples ou mal écrits
    (deezer("Under Pressure", "Queen & David Bowie"), deezer("Under Pressure", "David Bowie")),
    (deezer("September", "Earth, Wind & Fire"), deezer("September", "Earth Wind and Fire")),
    (deezer("Toxic", "Britney Spears"), deezer("Toxic", "Brittney Spears")),
    (deezer("Grenade", "Bruno Mars"), deezer("Grenade", "Bruno Mars Official")),
    # Versions qui restent la même chanson
    (deezer("Hey Jude", "The Beatles"), deezer("Hey Jude - Remastered 2015", "The Beatles")),
    (deezer("Hey Jude", "The Beatles"), deezer("Hey Jude (2015 Remaster)", "The Beatles")),
    (deezer("Wonderwall", "Oasis"), deezer("Wonderwall (Live at Knebworth)", "Oasis")),
    (deezer("Wonderwall", "Oasis"), deezer("Wonderwall - Live", "Oasis")),
    (deezer("Layla", "Eric Clapton"), deezer("Layla (Acoustic)", "Eric Clapton")),
    (deezer("Alors on danse", "Stromae"), deezer("Alors on danse - Radio Edit", "Stromae")),
    (deezer("Thriller", "Michael Jackson"), deezer("Thriller (From the album)", "Michael Jackson")),
    (youtube("Let It Be", "Channel A", duration_seconds=240), youtube("Let It Be", "Channel B", duration_seconds=241)),
    # Sous-titre omis d'un côté
    (deezer("(I Can't Get No) Satisfaction", "The Rolling Stones"), deezer("Satisfaction", "Rolling Stones")),
    (deezer("Sweet Dreams (Are Made of This)", "Eurythmics"), deezer("Sweet Dreams", "Eurythmics")),
    # Artiste invérifiable mais durée identique
    (deezer("Mr. Brightside", "The Killers", duration_seconds=223), youtube("Mr. Brightside", "Rock Classics", duration_seconds=224)),
    # Identifiants, quels que soient les textes
    (deezer("A", "B", youtube_video_id="vid"), deezer("C", "D", youtube_video_id="vid")),
    (deezer("A", "B", isrc="USUM71703861"), deezer("C", "D", isrc="usum71703861 ")),
]

DIFFERENT = [
    # Homonymes
    (deezer("Hello", "Adele"), deezer("Hello", "Lionel Richie")),
    (deezer("Stay", "Rihanna"), deezer("Stay", "Zedd")),
    (deezer("Hurt", "Johnny Cash"), deezer("Hurt", "Christina Aguilera")),
    (deezer("Hello", "Adele"), youtube("Hello", "Random Uploader")),
    (youtube("Hello", "Channel A"), youtube("Hello", "Channel B")),
    (deezer("Thriller", "Michael Jackson"), deezer("Thriller", "Janet Jackson")),
    (deezer("Hello", "Adele", duration_seconds=300), deezer("Hello", "Lionel Richie", duration_seconds=300)),
    (deezer("Mr. Brightside", "The Killers", duration_seconds=223), deezer("Mr. Brightside", "Someone Else", duration_seconds=223)),
    (deezer("Hello", "Adele", duration_seconds=300), youtube("Hello", "Random Uploader", duration_seconds=300)),
    # Suites et chansons voisines
    (deezer("Another Brick in the Wall, Pt. 1", "Pink Floyd"), deezer("Another Brick in the Wall, Pt. 2", "Pink Floyd")),
    (deezer("Another Brick in the Wall (Part 1)", "Pink Floyd"), deezer("Another Brick in the Wall (Part 2)", "Pink Floyd")),
    (deezer("Symphony No. 5", "Beethoven"), deezer("Symphony No. 6", "Beethoven")),
    (deezer("Love Me Do", "The Beatles"), deezer("Love Me Too", "The Beatles")),
    (deezer("Love Me", "Artist"), deezer("Love Me Do", "Artist")),
    (deezer("Thank You for the Music", "ABBA"), deezer("Thank You for the", "ABBA")),
    # Versions distinctes
    (deezer("Levels", "Avicii"), deezer("Levels (Skrillex Remix)", "Avicii")),
    (deezer("Levels (Skrillex Remix)", "Avicii"), deezer("Levels (Tiesto Remix)", "Avicii")),
    (deezer("Levels", "Avicii"), deezer("Levels - Radio Remix", "Avicii")),
    (deezer("Levels", "Avicii"), youtube("Avicii - Levels (Nightcore)", "Avicii")),
    (deezer("Hello", "Adele"), deezer("Hello (Instrumental)", "Adele")),
    (deezer("Hello", "Adele"), deezer("Hello (Karaoke Version)", "Adele")),
    (deezer("Hello", "Adele"), deezer("Hello (Acoustic Cover)", "Adele")),
    (deezer("Hello", "Adele"), deezer("Hello (Sped Up)", "Adele")),
    # Reprise par un autre artiste
    (deezer("Hallelujah", "Leonard Cohen"), deezer("Hallelujah", "Jeff Buckley")),
    # Sous-titres différents chez un même artiste
    (deezer("Intro (Paris)", "Artist"), deezer("Intro (Tokyo)", "Artist")),
    # Mentions de version qui font partie du vrai titre
    (deezer("Live Forever", "Oasis"), deezer("Forever", "Oasis")),
    (deezer("Video Games", "Lana Del Rey"), deezer("Games", "Lana Del Rey")),
    (deezer("Radio Ga Ga", "Queen"), deezer("Radio", "Queen")),
    (deezer("Single Ladies", "Beyoncé"), deezer("Halo", "Beyoncé")),
    # Même chaîne ou même artiste : le segment commun n'est pas un titre
    (youtube("Daft Punk - Get Lucky", "SomeChannel"), youtube("Daft Punk - One More Time", "SomeChannel")),
    (youtube("Get Lucky - Daft Punk", "SomeChannel"), youtube("One More Time - Daft Punk", "SomeChannel")),
    (youtube("Queen - One More Time", "Channel A"), youtube("Britney Spears - One More Time", "Channel B")),
    # Titre de trois mots sans preuve d'artiste : homonymes ou reprises
    (youtube("Let It Be", "Channel A", duration_seconds=240), youtube("Let It Be", "Channel B", duration_seconds=200)),
    (youtube("Let It Be", "Channel A"), youtube("Let It Be", "Channel B")),
    # Suffixes différents d'un même titre
    (deezer("Song - Paris Mix Tape", "Artist"), deezer("Song - Tokyo Mix Tape", "Artist")),
    # Le dakuten change le mot, contrairement à un accent latin
    (deezer("はる", "YOASOBI"), deezer("ばる", "YOASOBI")),
    # Champs vides
    (deezer("", "Artist"), deezer("", "Artist")),
    (deezer("Title", ""), deezer("Title", "")),
    (deezer("   ", "   "), deezer("   ", "   ")),
    (deezer("Song", "Artist"), deezer("", "Artist")),
]


@pytest.mark.parametrize("a,b", SAME)
def test_same_song(a, b):
    assert same_song(a, b)
    assert same_song(b, a)


@pytest.mark.parametrize("a,b", DIFFERENT)
def test_different_songs(a, b):
    assert not same_song(a, b)
    assert not same_song(b, a)


def test_non_latin_titles_are_compared():
    assert same_song(deezer("夜に駆ける", "YOASOBI"), youtube("YOASOBI - 夜に駆ける", "Channel"))
    assert not same_song(deezer("夜に駆ける", "YOASOBI"), deezer("群青", "YOASOBI"))


def test_song_id_is_the_smallest_track_id_of_the_group():
    songs = group_songs([
        SongTrack(id=9, title="Get Lucky", artist="Daft Punk"),
        SongTrack(id=4, title="Hello", artist="Adele"),
        SongTrack(id=2, title="Get Lucky", artist="Daft Punk"),
    ])
    assert songs == {9: 2, 4: 4, 2: 2}


def test_three_way_merge_across_sources():
    songs = group_songs([
        SongTrack(id=1, title="Get Lucky", artist="Daft Punk", isrc="X"),
        SongTrack(id=2, title="Totally different label", artist="Unknown", isrc="X"),
        SongTrack(id=3, title="Daft Punk - Get Lucky", artist="Chan", structured=False),
    ])
    assert len(set(songs.values())) == 1


def test_no_tracks():
    assert group_songs([]) == {}


def test_5000_tracks_cluster_quickly():
    rng = random.Random(0)
    artists = [f"Artist Number {i}" for i in range(150)]
    words = ["love", "night", "dream", "fire", "heart", "dance", "rain", "gold", "wild", "river", "home", "light"]
    tracks = []
    for track_id in range(5000):
        title = " ".join(rng.choices(words, k=3)) + f" {rng.randrange(40)}"
        if track_id % 2:
            tracks.append(SongTrack(id=track_id, title=title, artist=rng.choice(artists)))
        else:
            tracks.append(SongTrack(
                id=track_id, title=f"{rng.choice(artists)} - {title} (Official Video)", artist="Channel", structured=False,
            ))
    started = time.perf_counter()
    group_songs(tracks)
    assert time.perf_counter() - started < 2.0
