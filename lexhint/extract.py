from __future__ import annotations

from collections.abc import Iterator, Mapping

from .languages import normalize_language
from .models import (
    DictionaryEntry,
    Example,
    ExtractionDiagnostics,
    Form,
    HeadwordRelation,
    Pronunciation,
    RelatedTerm,
    Sense,
)
from .store import normalize_display_word
from .wiktextract_types import RETAINED_ENTRY_FIELDS, RETAINED_SENSE_FIELDS


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    result: list[str] = []
    for item in value:
        if isinstance(item, str) and item and item not in result:
            result.append(item)
    return tuple(result)


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _examples(value: object) -> tuple[Example, ...]:
    if not isinstance(value, list):
        return ()
    result: list[Example] = []
    for item in value:
        text: str | None
        translation: str | None
        if isinstance(item, str):
            text = item
            translation = None
        elif isinstance(item, Mapping):
            text = _text(item.get("text"))
            translation = _text(item.get("translation"))
        else:
            continue
        if text is None:
            continue
        example = Example(text, translation)
        if example not in result:
            result.append(example)
    return tuple(result)


def _related(value: object, relation: str) -> tuple[str | RelatedTerm, ...]:
    if not isinstance(value, list):
        return ()
    result: list[str | RelatedTerm] = []
    for item in value:
        if isinstance(item, str):
            if item and item not in result:
                result.append(item)
        elif isinstance(item, Mapping):
            word = _text(item.get("word"))
            if word:
                tags = _strings(item.get("tags"))
                related: str | RelatedTerm = RelatedTerm(word, relation, tags) if tags else word
                if related not in result:
                    result.append(related)
    return tuple(result)


def _forms(value: object) -> tuple[Form, ...]:
    if not isinstance(value, list):
        return ()
    result: list[Form] = []
    for item in value:
        form: str | None
        tags: tuple[str, ...]
        if isinstance(item, str):
            form = item
            tags = ()
        elif isinstance(item, Mapping):
            form = _text(item.get("form"))
            tags = _strings(item.get("tags"))
        else:
            continue
        if form:
            parsed = Form(form, tags)
            if parsed not in result:
                result.append(parsed)
    return tuple(result)


def _pronunciations(value: object) -> tuple[Pronunciation, ...]:
    if not isinstance(value, list):
        return ()
    result: list[Pronunciation] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        ipa = _text(item.get("ipa"))
        if ipa is None:
            continue
        pronunciation = Pronunciation(ipa=ipa, tags=_strings(item.get("tags")))
        if pronunciation not in result:
            result.append(pronunciation)
    return tuple(result)


def _relation_values(value: object) -> tuple[tuple[str, tuple[str, ...]], ...]:
    if not isinstance(value, list):
        return ()
    result: list[tuple[str, tuple[str, ...]]] = []
    for item in value:
        word: str | None
        tags: tuple[str, ...]
        if isinstance(item, str):
            word = item
            tags = ()
        elif isinstance(item, Mapping):
            word = _text(item.get("word")) or _text(item.get("target"))
            tags = _strings(item.get("tags"))
        else:
            continue
        if word:
            value_pair = (word, tags)
            if value_pair not in result:
                result.append(value_pair)
    return tuple(result)


def _sense(
    raw: Mapping[str, object],
    entry_topics: tuple[str, ...],
    diagnostics: ExtractionDiagnostics | None = None,
) -> Sense | None:
    if diagnostics is not None:
        diagnostics.senses_seen += 1
    sense = Sense(
        glosses=_strings(raw.get("glosses")),
        topics=tuple(dict.fromkeys(entry_topics + _strings(raw.get("topics")))),
        tags=_strings(raw.get("tags")),
        examples=_examples(raw.get("examples")),
        synonyms=_related(raw.get("synonyms"), "synonym"),
        antonyms=_related(raw.get("antonyms"), "antonym"),
    )
    if not any((sense.glosses, sense.topics, sense.examples, sense.synonyms, sense.antonyms)):
        if diagnostics is not None:
            diagnostics.senses_without_retained_content += 1
        return None
    if diagnostics is not None:
        diagnostics.senses_retained += 1
    return sense


def relation_candidates(
    entry: Mapping[str, object], *, language: str
) -> tuple[HeadwordRelation, ...]:
    """Extract explicit headword relations without changing dictionary entries."""
    base_language = normalize_language(language)
    if str(entry.get("lang_code") or "").lower() != base_language:
        return ()
    source = normalize_display_word(str(entry.get("word") or ""))
    if not source:
        return ()
    result: list[HeadwordRelation] = []

    def add(target: str, relation: str, tags: tuple[str, ...] = ()) -> None:
        normalized_target = normalize_display_word(target)
        if not normalized_target or normalized_target == source:
            return
        for index, existing in enumerate(result):
            if (
                existing.source == source
                and existing.target == normalized_target
                and existing.relation == relation
            ):
                merged_tags = tuple(dict.fromkeys(existing.tags + tags))
                result[index] = HeadwordRelation(source, normalized_target, relation, merged_tags)
                return
        result.append(HeadwordRelation(source, normalized_target, relation, tags))

    for target, tags in _relation_values(entry.get("redirects")):
        add(target, "redirect", tags)
    raw_senses = entry.get("senses")
    if isinstance(raw_senses, list):
        for raw_sense in raw_senses:
            if not isinstance(raw_sense, Mapping):
                continue
            for target, tags in _relation_values(raw_sense.get("alt_of")):
                add(target, "alternative", tags)
            for target, tags in _relation_values(raw_sense.get("form_of")):
                add(target, "form_of", tags)
    return tuple(result)


def dictionary_entries(
    entry: Mapping[str, object],
    *,
    language: str,
    diagnostics: ExtractionDiagnostics | None = None,
) -> Iterator[DictionaryEntry]:
    """Convert one source entry to the curated Lexhint dictionary model."""
    if diagnostics is not None:
        diagnostics.source_records += 1
        diagnostics.record_fields(set(entry), set(RETAINED_ENTRY_FIELDS) & set(entry))
    base_language = normalize_language(language)
    if str(entry.get("lang_code") or "").lower() != base_language:
        return
    if diagnostics is not None:
        diagnostics.language_records += 1

    display_word = normalize_display_word(str(entry.get("word") or ""))
    if not display_word:
        if diagnostics is not None:
            diagnostics.entries_without_word += 1
        return
    raw_senses = entry.get("senses")
    if not isinstance(raw_senses, list):
        if diagnostics is not None:
            diagnostics.entries_without_senses += 1
        return

    entry_topics = _strings(entry.get("topics"))
    senses: list[Sense] = []
    for raw_sense in raw_senses:
        if isinstance(raw_sense, Mapping):
            parsed = _sense(raw_sense, entry_topics, diagnostics)
            if parsed is not None:
                senses.append(parsed)
    if not senses:
        if diagnostics is not None:
            diagnostics.entries_without_senses += 1
        return

    forms = _forms(entry.get("forms"))
    pronunciations = _pronunciations(entry.get("sounds"))
    etymology = _text(entry.get("etymology_text")) or _text(entry.get("etymology"))
    relations = relation_candidates(entry, language=base_language)
    if diagnostics is not None:
        diagnostics.accepted_entries += 1
        diagnostics.accepted_senses += len(senses)
        diagnostics.entries_with_etymology += int(etymology is not None)
        diagnostics.entries_with_forms += int(bool(forms))
        diagnostics.entries_with_ipa += int(bool(pronunciations))
        diagnostics.entries_with_relations += int(bool(relations))
        diagnostics.relation_candidates += len(relations)
        for raw_sense in raw_senses:
            if isinstance(raw_sense, Mapping):
                fields = set(raw_sense)
                diagnostics.record_fields(fields, set(RETAINED_SENSE_FIELDS) & fields)

    yield DictionaryEntry(
        word=display_word,
        pos=str(entry.get("pos") or ""),
        senses=tuple(senses),
        forms=forms,
        pronunciations=pronunciations,
        etymology=etymology,
    )


__all__ = ["dictionary_entries", "relation_candidates"]
