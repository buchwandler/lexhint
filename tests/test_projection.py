import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from lexhint import Lexicon, LexiconCapabilityError, project_artifact
from lexhint.builder import build_dictionary
from lexhint.cli import main
from lexhint.status import read_artifact_status

FIXTURE = Path(__file__).parent / "fixtures" / "kaikki-rich.jsonl"


@pytest.fixture
def rich_artifact(tmp_path: Path) -> Path:
    path, _ = build_dictionary(
        "en", FIXTURE, output=tmp_path / "rich.sqlite3", profile="rich", no_frequency=True
    )
    return path


def test_project_runtime_and_lexical_from_rich(rich_artifact: Path, tmp_path: Path) -> None:
    runtime = project_artifact(
        rich_artifact, output=tmp_path / "runtime.sqlite3", profile="runtime"
    )
    dictionary = project_artifact(
        rich_artifact,
        output=tmp_path / "dictionary.sqlite3",
        capabilities="lexical,semantic,dictionary",
    )
    lexical = project_artifact(
        rich_artifact, output=tmp_path / "lexical.sqlite3", capabilities="lexical"
    )

    lexical_search = project_artifact(
        rich_artifact, output=tmp_path / "lexical-search.sqlite3", capabilities="lexical,search"
    )
    dictionary_search = project_artifact(
        rich_artifact,
        output=tmp_path / "dictionary-search.sqlite3",
        capabilities="lexical,dictionary,search",
    )
    runtime_lexicon = Lexicon.from_path(runtime)
    lexical_lexicon = Lexicon.from_path(lexical)
    lexical_search_lexicon = Lexicon.from_path(lexical_search)
    dictionary_lexicon = Lexicon.from_path(dictionary)
    dictionary_search_lexicon = Lexicon.from_path(dictionary_search)
    rich_lexicon = Lexicon.from_path(rich_artifact)
    assert runtime_lexicon.capabilities == ("lexical", "semantic")
    assert dictionary_lexicon.capabilities == ("lexical", "semantic", "dictionary")
    assert lexical_lexicon.capabilities == ("lexical",)
    assert lexical_search_lexicon.capabilities == ("lexical", "search")
    assert dictionary_search_lexicon.capabilities == ("lexical", "dictionary", "search")
    assert lexical_search_lexicon.suggest("lov") == ("love",)
    assert dictionary_lexicon.entries("love")
    assert dictionary_lexicon.context_domains("music love", target=(6, 10)) == ()
    assert dictionary_lexicon.complete("lov") == ("love",)
    with pytest.raises(LexiconCapabilityError):
        dictionary_lexicon.suggest("lov")
    with pytest.raises(LexiconCapabilityError):
        dictionary_lexicon.search_definitions("love")
    assert runtime_lexicon.contains("love") == rich_lexicon.contains("love")
    assert runtime_lexicon.context_domains(
        "music love", target=(6, 10)
    ) == rich_lexicon.context_domains("music love", target=(6, 10))
    with pytest.raises(LexiconCapabilityError):
        lexical_lexicon.entries("love")
    with pytest.raises(LexiconCapabilityError):
        lexical_lexicon.context_domains("music love", target=(6, 10))

    metadata = dict(runtime_lexicon.metadata)
    assert metadata["projected_from_capabilities"] == "lexical,semantic,dictionary,search"
    assert metadata["projected_from_sha256"]
    assert read_artifact_status(path=runtime).counts["entries"] is None
    with closing(sqlite3.connect(dictionary)) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
    assert "entries" in tables
    assert "senses" in tables
    assert "sense_topics" in tables
    assert "lexeme_ngrams" not in tables
    assert "sense_search_terms" not in tables


def test_project_rejects_non_subset_and_same_path(rich_artifact: Path, tmp_path: Path) -> None:
    runtime, _ = build_dictionary(
        "en",
        FIXTURE,
        output=tmp_path / "runtime-source.sqlite3",
        profile="runtime",
        no_frequency=True,
    )
    with pytest.raises(ValueError, match="subset"):
        project_artifact(runtime, output=tmp_path / "bad.sqlite3", profile="rich")
    with pytest.raises(ValueError, match="differ"):
        project_artifact(rich_artifact, output=rich_artifact, profile="runtime")


def test_project_cli(
    tmp_path: Path, rich_artifact: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "runtime.sqlite3"
    assert (
        main(
            [
                "dictionary",
                "project",
                str(rich_artifact),
                "--output",
                str(output),
                "--profile",
                "runtime",
            ]
        )
        == 0
    )
    assert output.is_file()
    assert "Projected Lexhint database" in capsys.readouterr().out
