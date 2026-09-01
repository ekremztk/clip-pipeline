"""
One spelling per person.

The Cast Library groups clips by the name typed into "Main Person" on the job
form. Typed by hand, twice, weeks apart, the same guest arrives as "Dolly
Parton", "dolly parton " and "Dolly  Parton" — three names, three cards, one
person. This collapses the differences that are certainly accidental.

Casing is deliberately NOT forced. Title-casing would turn "Neil deGrasse
Tyson" into "Neil Degrasse Tyson", so the stored value keeps whatever was
typed and the Cast Library query groups case-insensitively instead.
"""

import re

_WHITESPACE = re.compile(r"\s+")


def normalize_person_name(value: str | None) -> str | None:
    """Trim, collapse internal whitespace runs. Returns None for anything empty."""
    if not value:
        return None
    cleaned = _WHITESPACE.sub(" ", value).strip()
    return cleaned or None
