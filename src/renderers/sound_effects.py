"""Resolve semantic sound cues to the bundled Jianying sound-effect library."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

from ..core.models import LayoutResult


REFERENCE_DRAFT = Path("audio/sound_effect/音频和文字/draft_info.json")
LIBRARY_FOLDER = Path("audio/sound_effect/library")

LOCAL_FILE_NAMES = {
    "啵1": "pop_1.mp3",
    "仙尘音效": "fairy_dust.mp3",
    "唰": "swish.mp3",
    "Ding，可爱提示音": "cute_ding.mp3",
    "Magic reveal": "magic_reveal.mp3",
    "滴，提示音": "drop_hint.mp3",
    "啾": "chirp.mp3",
    "提示音": "hint.mp3",
    "卡通弹跳音1": "cartoon_bounce_1.mp3",
    "魔法音效": "magic.mp3",
    "闪亮登场音效": "sparkle_reveal.mp3",
    "卡通弹跳音2": "cartoon_bounce_2.mp3",
    "咻，抛物弹簧音": "spring_whoosh.mp3",
    "啵，轻气泡音3": "light_bubble_3.mp3",
}

CUE_SOURCE_NAMES = {
    "pop": ("啵1", "卡通弹跳音1", "卡通弹跳音2", "啵，轻气泡音3"),
    "swish": ("唰", "咻，抛物弹簧音", "啾"),
    "chime": ("滴，提示音", "提示音", "Ding，可爱提示音"),
    "reveal": ("Magic reveal", "魔法音效", "闪亮登场音效", "仙尘音效"),
}

CUE_VOLUME = {
    "pop": 0.30,
    "swish": 0.24,
    "chime": 0.22,
    "reveal": 0.20,
}

CUE_MAX_DURATION_MS = {
    "pop": 650,
    "swish": 780,
    "chime": 820,
    "reveal": 880,
}


@dataclass(frozen=True)
class ReferenceSound:
    name: str
    path: Path
    duration_ms: int


@dataclass(frozen=True)
class SoundAsset:
    name: str
    path: Path


@dataclass(frozen=True)
class SoundEvent:
    element_id: str
    cue: str
    start_ms: int


def load_reference_sounds(draft_info: Path) -> dict[str, ReferenceSound]:
    data = json.loads(draft_info.read_text(encoding="utf-8"))
    sounds: dict[str, ReferenceSound] = {}
    for item in data.get("materials", {}).get("audios", []):
        name = str(item.get("name", "")).strip()
        raw_path = str(item.get("path", "")).strip()
        if not name or not raw_path:
            continue
        sounds[name] = ReferenceSound(
            name=name,
            path=Path(raw_path).expanduser(),
            duration_ms=max(0, int(item.get("duration", 0)) // 1000),
        )
    return sounds


def load_sound_library(project_root: Path) -> dict[str, tuple[SoundAsset, ...]]:
    reference_path = project_root / REFERENCE_DRAFT
    reference = load_reference_sounds(reference_path) if reference_path.exists() else {}
    library: dict[str, tuple[SoundAsset, ...]] = {}
    for cue, source_names in CUE_SOURCE_NAMES.items():
        assets: list[SoundAsset] = []
        for source_name in source_names:
            local_name = LOCAL_FILE_NAMES[source_name]
            local_path = project_root / LIBRARY_FOLDER / local_name
            if local_path.exists():
                assets.append(SoundAsset(source_name, local_path))
                continue
            reference_sound = reference.get(source_name)
            if reference_sound is not None and reference_sound.path.exists():
                assets.append(SoundAsset(source_name, reference_sound.path))
        library[cue] = tuple(assets)
    return library


def collect_sound_events(result: LayoutResult) -> list[SoundEvent]:
    events = [
        SoundEvent(
            element_id=element.element_id,
            cue=str(element.metadata["sound_effect"]),
            start_ms=element.start_ms,
        )
        for element in result.elements
        if element.metadata.get("sound_effect")
    ]
    return sorted(events, key=lambda event: (event.start_ms, event.element_id))


def choose_sound_asset(
    event: SoundEvent,
    library: dict[str, tuple[SoundAsset, ...]],
    *,
    previous_path: Path | None = None,
) -> SoundAsset | None:
    assets = library.get(event.cue, ())
    if not assets:
        return None
    digest = hashlib.sha256(f"{event.element_id}:{event.start_ms}:{event.cue}".encode("utf-8")).digest()
    index = int.from_bytes(digest[:8], "big") % len(assets)
    if previous_path is not None and len(assets) > 1 and assets[index].path == previous_path:
        index = (index + 1) % len(assets)
    return assets[index]
