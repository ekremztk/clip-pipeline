"""
Layer 3 — Composition Optimization
Converts a PersonDetection into an optimal crop X position.

Key insight: simply centering the face is wrong for side-facing subjects.
A person looking left needs space to their left (look room), so the crop
window shifts left to give visual breathing room in the direction of gaze.
"""
from typing import Optional

import numpy as np

from app.reframe.models.types import PersonDetection


# How far to shift the crop window in the gaze direction,
# as a fraction of the crop window width.
# 0.10 = shift 10% of crop_w toward gaze direction.
LOOK_ROOM_FRACTION = 0.10


def compute_crop_width(src_w: int, src_h: int, aspect_ratio: str) -> int:
    """
    Calculate the crop window width in pixels for the given target aspect ratio.
    The crop window always spans the full source height.

    aspect_ratio format: "W:H" (e.g. "9:16", "1:1", "4:5", "16:9")
    """
    try:
        w_part, h_part = (int(x) for x in aspect_ratio.split(":"))
    except Exception:
        w_part, h_part = 9, 16  # default to 9:16

    # crop_w / src_h == w_part / h_part
    crop_w = int(src_h * w_part / h_part)

    # For 16:9 source to 16:9 target: no horizontal crop needed
    crop_w = min(crop_w, src_w)
    return crop_w


def compute_crop_x(
    person: PersonDetection,
    src_w: int,
    src_h: int,
    aspect_ratio: str = "9:16",
) -> int:
    """
    Compute the optimal crop window left-edge X (pixels) for one person.

    Steps:
      1. Convert normalized face center to pixel coordinates
      2. Basic centering: crop_x = face_px - crop_w / 2
      3. Apply look room: shift toward gaze direction by LOOK_ROOM_FRACTION * crop_w
      4. Clamp to valid range [0, src_w - crop_w]
    """
    crop_w = compute_crop_width(src_w, src_h, aspect_ratio)

    face_px = person.cx_norm * src_w
    base_x = face_px - crop_w / 2.0

    look_room_px = LOOK_ROOM_FRACTION * crop_w
    gaze = person.gaze_direction

    if gaze == "left":
        adjusted_x = base_x - look_room_px   # shift crop left → more space to the left
    elif gaze == "right":
        adjusted_x = base_x + look_room_px   # shift crop right → more space to the right
    else:
        adjusted_x = base_x                  # center / frontal / unknown: no shift

    return int(np.clip(adjusted_x, 0, src_w - crop_w))


def center_crop_x(src_w: int, src_h: int, aspect_ratio: str = "9:16") -> int:
    """
    Returns the centered crop X when no person is detected.
    Used as fallback / hold position.
    """
    crop_w = compute_crop_width(src_w, src_h, aspect_ratio)
    return int(np.clip(src_w / 2.0 - crop_w / 2.0, 0, src_w - crop_w))
