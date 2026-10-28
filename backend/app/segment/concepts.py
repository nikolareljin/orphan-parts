"""What to look for in a photo, as the short noun phrases SAM 3.1 takes one at a time.

A concept key is what the rest of the app and the UI use; the phrase is what the model sees.
Category profiles will carry their own concepts later; until then this table covers the first
category and the fallback, and an unknown key is sent as its own phrase.
"""

CONCEPTS: dict[str, str] = {
    "item": "the main object",
    "label": "product label with printed text",
    "connector": "plug or connector at the end of a cable",
    "opening": "round opening of a hose or tube",
}

DEFAULT_CONCEPTS: tuple[str, ...] = ("item", "label", "connector")
MAX_CONCEPTS = 6


def phrase_for(key: str) -> str:
    return CONCEPTS.get(key, key)
