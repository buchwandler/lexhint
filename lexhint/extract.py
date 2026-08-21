from __future__ import annotations

from collections.abc import Iterator, Mapping

from .languages import normalize_language
from .models import DictionaryEntry, Example, Form, Pronunciation, RelatedTerm, Sense
from .store import normalize_display_word


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


def _sense(raw: Mapping[str, object], entry_topics: tuple[str, ...]) -> Sense | None:
    sense = Sense(
        glosses=_strings(raw.get("glosses")),
        topics=tuple(dict.fromkeys(entry_topics + _strings(raw.get("topics")))),
        tags=_strings(raw.get("tags")),
        examples=_examples(raw.get("examples")),
        synonyms=_related(raw.get("synonyms"), "synonym"),
        antonyms=_related(raw.get("antonyms"), "antonym"),
    )
    if not any((sense.glosses, sense.topics, sense.examples, sense.synonyms, sense.antonyms)):
        return None
    return sense


def dictionary_entries(entry: Mapping[str, object], *, language: str) -> Iterator[DictionaryEntry]:
    """Convert one source entry to the curated Lexhint dictionary model."""
    base_language = normalize_language(language)
    if str(entry.get("lang_code") or "").lower() != base_language:
        return

    display_word = normalize_display_word(str(entry.get("word") or ""))
    if not display_word:
        return
    raw_senses = entry.get("senses")
    if not isinstance(raw_senses, list):
        return

    entry_topics = _strings(entry.get("topics"))
    senses: list[Sense] = []
    for raw_sense in raw_senses:
        if isinstance(raw_sense, Mapping):
            parsed = _sense(raw_sense, entry_topics)
            if parsed is not None:
                senses.append(parsed)
    if not senses:
        return

    etymology = _text(entry.get("etymology_text")) or _text(entry.get("etymology"))
    yield DictionaryEntry(
        word=display_word,
        pos=str(entry.get("pos") or ""),
        senses=tuple(senses),
        forms=_forms(entry.get("forms")),
        pronunciations=_pronunciations(entry.get("sounds")),
        etymology=etymology,
    )


__all__ = ["dictionary_entries"]
