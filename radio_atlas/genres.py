"""Curated genres mapped to Radio Browser tags."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Genre:
    name: str
    tag: str


GENRES: tuple[Genre, ...] = (
    Genre("80s", "80s"),
    Genre("Alternative", "alternative"),
    Genre("Ambient", "ambient"),
    Genre("Blues", "blues"),
    Genre("Chillout", "chillout"),
    Genre("Classical", "classical"),
    Genre("Country", "country"),
    Genre("Cumbia", "cumbia"),
    Genre("Dance", "dance"),
    Genre("Electronic", "electronic"),
    Genre("Folk", "folk"),
    Genre("Funk", "funk"),
    Genre("Gospel", "gospel"),
    Genre("Hip-Hop", "hip-hop"),
    Genre("House", "house"),
    Genre("Indie", "indie"),
    Genre("Jazz", "jazz"),
    Genre("Latin", "latin"),
    Genre("Metal", "metal"),
    Genre("News", "news"),
    Genre("Oldies", "oldies"),
    Genre("Pop", "pop"),
    Genre("Punk", "punk"),
    Genre("Rap", "rap"),
    Genre("Reggae", "reggae"),
    Genre("Reggaeton", "reggaeton"),
    Genre("Rock", "rock"),
    Genre("Salsa", "salsa"),
    Genre("Soul", "soul"),
    Genre("Sports", "sports"),
    Genre("Talk", "talk"),
    Genre("Techno", "techno"),
)

GENRE_BY_TAG: dict[str, Genre] = {genre.tag: genre for genre in GENRES}


def genre_for_tag(tag: str) -> Genre | None:
    return GENRE_BY_TAG.get(tag.strip().casefold())
