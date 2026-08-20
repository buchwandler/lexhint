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
    lexical = project_artifact(
        rich_artifact, output=tmp_path / "lexical.sqlite3", capabilities="lexical"
    )

    runtime_lexicon = Lexicon.from_path(runtime)
    lexical_lexicon = Lexicon.from_path(lexical)
    rich_lexicon = Lexicon.from_path(rich_artifact)
    assert runtime_lexicon.capabilities == ("lexical", "semantic")
    assert lexical_lexicon.capabilities == ("lexical",)
    assert runtime_lexicon.contains("love") == rich_lexicon.contains("love")
    assert runtime_lexicon.context_domains(
        "music love", target=(6, 10)
    ) == rich_lexicon.context_domains("music love", target=(6, 10))
    with pytest.raises(LexiconCapabilityError):
        lexical_lexicon.entries("love")
    with pytest.raises(LexiconCapabilityError):
        lexical_lexicon.context_domains("music love", target=(6, 10))

    metadata = dict(runtime_lexicon.metadata)
    assert metadata["projected_from_capabilities"] == "lexical,semantic,dictionary"
    assert metadata["projected_from_sha256"]
    assert read_artifact_status(path=runtime).counts["entries"] is None


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
