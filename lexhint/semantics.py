from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Mapping

from .models import SemanticDomain
from .store import normalize_word

RAW_TOPIC_DOMAINS: Mapping[str, tuple[SemanticDomain, float]] = {
    "computing": (SemanticDomain.COMPUTING, 1.0),
    "computer-science": (SemanticDomain.COMPUTING, 1.0),
    "programming": (SemanticDomain.COMPUTING, 1.0),
    "software": (SemanticDomain.COMPUTING, 1.0),
    "communications": (SemanticDomain.COMMUNICATIONS, 1.0),
    "telecommunications": (SemanticDomain.COMMUNICATIONS, 1.0),
    "finance": (SemanticDomain.FINANCE, 1.0),
    "law": (SemanticDomain.LAW, 1.0),
    "sports": (SemanticDomain.SPORTS, 1.0),
    "association-football": (SemanticDomain.SPORTS, 1.0),
    "ball-games": (SemanticDomain.SPORTS, 0.9),
    "tennis": (SemanticDomain.SPORTS, 1.0),
    "racquet-sports": (SemanticDomain.SPORTS, 0.9),
    "music": (SemanticDomain.MUSIC, 1.0),
    "biology": (SemanticDomain.BIOLOGY, 1.0),
    "medicine": (SemanticDomain.MEDICINE, 1.0),
    "chemistry": (SemanticDomain.CHEMISTRY, 1.0),
    "geography": (SemanticDomain.GEOGRAPHY, 1.0),
}


def project_topics(topics: Iterable[str]) -> dict[SemanticDomain, tuple[float, tuple[str, ...]]]:
    projected: dict[SemanticDomain, tuple[float, tuple[str, ...]]] = {}
    for raw in topics:
        mapping = RAW_TOPIC_DOMAINS.get(raw.casefold())
        if mapping is None:
            continue
        domain, weight = mapping
        current = projected.get(domain)
        if current is None or weight > current[0]:
            projected[domain] = (weight, (raw,))
        elif weight == current[0] and raw not in current[1]:
            projected[domain] = (weight, current[1] + (raw,))
    return projected


def insert_lexeme_domains(
    connection: sqlite3.Connection,
    domains_by_word: Mapping[str, Iterable[str]],
) -> int:
    rows = 0
    for word, topics in domains_by_word.items():
        normalized = normalize_word(word)
        for domain, (weight, source_topics) in project_topics(topics).items():
            existing = connection.execute(
                "SELECT weight, source_topics FROM lexeme_domains WHERE word=? AND domain=?",
                (normalized, domain.value),
            ).fetchone()
            if existing is not None:
                previous_topics = json.loads(str(existing[1]))
                source_topics = tuple(sorted(set(previous_topics) | set(source_topics)))
                weight = max(weight, float(existing[0]))
            connection.execute(
                "INSERT OR REPLACE INTO lexeme_domains("
                "word, domain, weight, source_topics) VALUES (?, ?, ?, ?)",
                (
                    normalized,
                    domain.value,
                    weight,
                    json.dumps(source_topics, separators=(",", ":")),
                ),
            )
            rows += 1
    return rows
