"""Template definitions for the pipeline-only Caption Template V2 engine."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FontSpec:
    family: str
    design_size: float
    weight: int
    paths: tuple[str, ...]


@dataclass(frozen=True)
class StrokeSpec:
    color: str
    width_ratio: float
    alpha: float


@dataclass(frozen=True)
class ShadowSpec:
    color: str
    alpha: float
    smoothing: float
    distance: float
    angle: float


@dataclass(frozen=True)
class LayoutSpec:
    max_words_per_page: int
    max_width_ratio: float
    transform_x: float
    transform_y: float
    line_spacing: float
    letter_spacing: float
    align: str


@dataclass(frozen=True)
class KaraokeSpec:
    active_color: str
    inactive_color: str
    read_color: str
    animation_duration: float
    merge_keyword_style: bool


@dataclass(frozen=True)
class CaptionV2Template:
    key: str
    display_name: str
    source: str
    font: FontSpec
    fill_color: str
    fill_alpha: float
    stroke: StrokeSpec
    shadow: ShadowSpec
    layout: LayoutSpec
    karaoke: KaraokeSpec


MONTSERRAT_BOLD_PATHS = (
    "/app/app/captions/assets/Montserrat-Bold-v4.ttf",
    "backend/app/captions/assets/Montserrat-Bold-v4.ttf",
    "/usr/share/fonts/truetype/montserrat/Montserrat-Bold.ttf",
    "/Users/ekrem/Downloads/Montserrat/static/Montserrat-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
)


V2_TEMPLATES: dict[str, CaptionV2Template] = {
    "word_highlight_ii": CaptionV2Template(
        key="word_highlight_ii",
        display_name="Word Highlight II",
        source="Subtitle preset / Word Highlight II",
        font=FontSpec(
            family="Montserrat",
            design_size=15.0,
            weight=700,
            paths=MONTSERRAT_BOLD_PATHS,
        ),
        fill_color="#FFFFFF",
        fill_alpha=1.0,
        stroke=StrokeSpec(
            color="#000000",
            width_ratio=0.07999999821186066,
            alpha=1.0,
        ),
        shadow=ShadowSpec(
            color="#000000",
            alpha=0.24685639142990112,
            smoothing=0.45000001788139343,
            distance=5.0,
            angle=-45.0,
        ),
        layout=LayoutSpec(
            max_words_per_page=3,
            max_width_ratio=0.82,
            transform_x=0.0,
            transform_y=-0.18229166666666666,
            line_spacing=0.02,
            letter_spacing=0.0,
            align="center",
        ),
        karaoke=KaraokeSpec(
            active_color="#FFFF00",
            inactive_color="#FFFFFF",
            read_color="#FFFFFF",
            animation_duration=0.8,
            merge_keyword_style=False,
        ),
    ),
}

LEGACY_TEMPLATE_ALIASES = {
    "cap" + "cut" + "_word_highlight_ii": "word_highlight_ii",
}


def normalize_template_key(template_key: str) -> str:
    return LEGACY_TEMPLATE_ALIASES.get(template_key, template_key)


def is_v2_template(template_key: str) -> bool:
    return normalize_template_key(template_key) in V2_TEMPLATES


def get_v2_template(template_key: str) -> CaptionV2Template:
    return V2_TEMPLATES[normalize_template_key(template_key)]
