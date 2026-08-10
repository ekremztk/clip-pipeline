"""Template definitions for the Caption Template V3 engine.

V3 is a fork of the V2 engine, copied verbatim and then rebuilt for the
single-line centred style. It is a separate package on purpose: V2 drives a
live channel and must not change when this style is tuned.

Differences from V2, all expressed here or in the sibling renderer:
  - no stroke; the shadow alone separates the text from the frame
  - Anton instead of Montserrat Bold
  - one line only, with pages packed by character budget
  - vertically centred (transform_y = 0 puts the block at height/2)
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FontSpec:
    family: str
    capcut_size: float
    weight: int
    uppercase: bool
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
    max_words_per_line: int
    max_width_ratio: float
    transform_x: float
    transform_y: float
    line_spacing: float
    letter_spacing: float
    word_gap_ratio: float
    align: str
    # V3 additions. A page closes as soon as one more word would push it past
    # max_chars_per_page, so the caption reads at a steady width instead of
    # alternating between a two-word page and a six-word one.
    max_chars_per_page: int = 24
    # Single-line guarantee: a page that still measures wider than the frame
    # allows is shrunk rather than wrapped.
    single_line: bool = True
    min_shrink_scale: float = 0.72


@dataclass(frozen=True)
class KaraokeSpec:
    active_color: str
    inactive_color: str
    read_color: str
    animation_duration: float
    active_scale: float
    pop_in_duration: float
    pop_out_duration: float
    merge_keyword_style: bool


@dataclass(frozen=True)
class CaptionV3Template:
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


ANTON_PATHS = (
    "/app/app/captions/assets/Anton-Regular.ttf",
    "backend/app/captions/assets/Anton-Regular.ttf",
    "/usr/share/fonts/truetype/anton/Anton-Regular.ttf",
    "/Users/ekrem/Library/Fonts/Anton-Regular.ttf",
    # Last resort only — these are not Anton and will change the look.
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
)


V3_TEMPLATES: dict[str, CaptionV3Template] = {
    "yellow_center": CaptionV3Template(
        key="yellow_center",
        display_name="Yellow Center",
        source="TheYellow Cast — forked from CapCut Word Highlight II",
        font=FontSpec(
            family="Anton",
            # 12.96 * 1080 / 200 = 70 px, against V2's 76 px. Anton is a
            # condensed face, so it reads smaller than Montserrat at equal px.
            capcut_size=12.963,
            weight=400,
            uppercase=True,
            paths=ANTON_PATHS,
        ),
        fill_color="#FFFFFF",
        fill_alpha=1.0,
        stroke=StrokeSpec(
            color="#000000",
            width_ratio=0.0,
            alpha=0.0,
        ),
        shadow=ShadowSpec(
            color="#000000",
            # Carries the whole burden now that the stroke is gone: darker,
            # further out, and nearly hard-edged rather than a soft halo.
            alpha=0.85,
            smoothing=0.06,
            distance=9.0,
            angle=45.0,
        ),
        layout=LayoutSpec(
            max_words_per_page=6,
            # Word count never forces a break; the character budget governs.
            max_words_per_line=99,
            max_width_ratio=0.86,
            transform_x=0.0,
            transform_y=0.0,
            line_spacing=0.02,
            letter_spacing=0.0,
            word_gap_ratio=0.24,
            align="center",
            max_chars_per_page=24,
            single_line=True,
            min_shrink_scale=0.72,
        ),
        karaoke=KaraokeSpec(
            active_color="#F5D14E",
            inactive_color="#FFFFFF",
            read_color="#FFFFFF",
            animation_duration=0.24,
            active_scale=1.14,
            pop_in_duration=0.08,
            pop_out_duration=0.16,
            merge_keyword_style=False,
        ),
    ),
}


def is_v3_template(template_key: str) -> bool:
    return template_key in V3_TEMPLATES


def get_v3_template(template_key: str) -> CaptionV3Template:
    return V3_TEMPLATES[template_key]
