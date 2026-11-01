"""Playlists préparées du blind test classique.

Le jeu relit la liste en direct (`app/blindtest/preset_tracks.py`). Chaque
`<slug>.json`, produit par `scripts/snapshot_blindtest_presets.py` et relu par
un humain, sert de copie de secours et de référence pour les noms. Un preset
sans fichier n'est simplement pas proposé.
"""
import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

_DIRECTORY = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Preset:
    slug: str
    name: str
    playlist_id: str

    @property
    def path(self) -> Path:
        return _DIRECTORY / f"{self.slug}.json"

    @property
    def source_url(self) -> str:
        return f"preset:{self.slug}"


PRESETS: Tuple[Preset, ...] = (
    Preset("hits-60", "Hits années 60", "RDCLAK5uy_nK5Gc1RXC3Qj5f6q2q8yKSNHP9bc-5td0"),
    Preset("hits-70", "Hits années 70", "RDCLAK5uy_l9zGPtwEeIpwVXtBZ216yRhklsre5bbOM"),
    Preset("hits-80", "Hits années 80", "RDCLAK5uy_lMzHW51iFg1Kx0d_2EHpzbOgCrwtu8cgI"),
    Preset("hits-90", "Hits années 90", "RDCLAK5uy_nQkPLhMF6chdzKSlWdX8NHMrLVpdci-eU"),
    Preset("classiques-intemporels", "Classiques intemporels", "RDCLAK5uy_mRnjSZUMjbxdR4MSK_YtcQU-A0-X-9chA"),
    Preset("tubes-pop", "Meilleurs tubes pop", "RDCLAK5uy_nmS3YoxSwVVQk9lEQJ0UX4ZCjXsW_psU8"),
    Preset("rock-hits", "Rock Hits", "RDCLAK5uy_lp8tPFzyN4a4WCduH0qFXPkKKCoToirTE"),
    Preset("hip-hop-classics", "Hip-hop Classics", "RDCLAK5uy_kP2172rQNb3KFXz880xp6M98R_ME5CIKA"),
    Preset("tubes-francophones", "Tubes francophones", "RDCLAK5uy_mn6mX0GYERCgJxFbmlSXE8Vxqhafy1VoY"),
    Preset("rap-francais", "Classiques du rap français", "RDCLAK5uy_nwmU7GOH9bo9N3RB566bAfjrMTZHJ6AhY"),
)


def available_presets() -> List[Preset]:
    return [preset for preset in PRESETS if preset.path.exists()]


def find_preset(slug: str) -> Optional[Preset]:
    return next((preset for preset in available_presets() if preset.slug == slug), None)


def preset_from_source_url(source_url: str) -> Optional[Preset]:
    return next((preset for preset in PRESETS if preset.source_url == source_url), None)


def load_tracks(preset: Preset) -> List[dict]:
    return json.loads(preset.path.read_text(encoding="utf-8"))["tracks"]
