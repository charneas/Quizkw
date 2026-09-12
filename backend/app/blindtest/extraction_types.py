"""Type de données commun retourné par chaque provider — évite un import
circulaire entre `providers/*.py` et `import_pipeline.py`."""
from dataclasses import dataclass
from typing import Optional


@dataclass
class ExtractedTrack:
    title: str
    artist: str
    isrc: Optional[str] = None
    youtube_video_id: Optional[str] = None
    source_url: Optional[str] = None
