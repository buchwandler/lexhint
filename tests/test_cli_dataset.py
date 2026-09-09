from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

import lexhint.cli as cli
import lexhint.datasets as datasets
from lexhint.builder import build_dictionary
from lexhint.cli import _parser, main

FIXTURE = Path(__file__).parent / "fixtures" / "kaikki-mini.jsonl"


def install_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source_variant: str = "native"
) -> None:
    monkeypatch.setenv("LEXHINT_DATA_DIR", str(tmp_path / "data"))
    source, _ = build_dictionary(
        "en",
        FIXTURE,
        output=tmp_path / "source.sqlite3",
        capabilities="lexical,semantic",
        no_frequency=True,
    )
    target = datasets._artifact_path("en", "runtime", "2026.08.20", source_variant=source_variant)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(source.read_bytes())
    artifact = datasets.DatasetArtifact(
        "en",
        "runtime",
        "2026.08.20",
        "data-2026.08.20",
        "2026-08-21T00:00:00Z",
        2,
        "10",
        "runtime",
        "full",
        ("lexical", "semantic"),
        1,
        target.stat().st_size,
        target.name,
        "fixture",
        "",
        source_variant=source_variant,
    )
    datasets._write_sidecar(target.with_name("artifact.json"), artifact, "2026-08-21T00:00:00Z")


def test_dataset_list_json_and_selector(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    install_runtime(tmp_path, monkeypatch)
    assert main(["--json", "dataset", "list"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["installed"][0]["selected"] is True
    assert main(["--json", "word", "compiler", "-l", "en", "--variant", "runtime"]) == 0
    assert json.loads(capsys.readouterr().out)["known"] is True


def test_path_and_variant_conflict_is_controlled(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["word", "compiler", "--path", str(tmp_path / "x"), "--variant", "rich"]) == 1
    assert "cannot be combined" in capsys.readouterr().err


def test_dictionary_variant_is_available_to_dataset_and_query_parsers() -> None:
    parser = _parser()
    download = parser.parse_args(["dataset", "download", "en", "--variant", "dictionary"])
    query = parser.parse_args(["word", "love", "-l", "en", "--variant", "dictionary"])
    assert download.variant == "dictionary"
    assert query.variant == "dictionary"


def test_source_variant_is_available_to_dataset_and_query_parsers() -> None:
    parser = _parser()
    download = parser.parse_args(["dataset", "download", "ceb", "--source-variant", "english"])
    query = parser.parse_args(
        ["dictionary", "search", "-l", "ceb", "--source-variant", "english", "Haus"]
    )
    short_english = parser.parse_args(["dataset", "download", "ceb", "-e"])
    short_native = parser.parse_args(["dictionary", "word", "Haus", "-l", "ceb", "-n"])
    assert download.source_variant == "english"
    assert query.source_variant == "english"
    assert short_english.source_variant == "english"
    assert short_native.source_variant == "native"


@pytest.mark.parametrize(
    "args",
    (
        ["dataset", "download", "ceb", "-e", "-n"],
        ["dataset", "download", "ceb", "-e", "--source-variant", "native"],
        ["dictionary", "word", "Haus", "-l", "ceb", "-n", "--source-variant", "english"],
    ),
)
def test_source_variant_aliases_conflict(args: list[str]) -> None:
    with pytest.raises(SystemExit):
        _parser().parse_args(args)


def test_dataset_available_cli_lists_all_schema10_languages(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    artifacts = tuple(
        datasets.DatasetArtifact(
            language,
            "runtime",
            "2026.08.28",
            f"data-{language}-2026.08.28",
            "2026-09-01T00:00:00Z",
            2,
            datasets.SCHEMA_VERSION,
            "runtime",
            "full",
            ("lexical", "semantic"),
            123,
            456,
            f"lexhint-{language}-runtime-s10-2026.08.28.sqlite3.gz",
            "a" * 64,
            "https://example.test/asset",
        )
        for language in ("cs", "de", "en")
    )
    monkeypatch.setattr("lexhint.cli.available_datasets", lambda **kwargs: artifacts)

    assert main(["dataset", "available"]) == 0
    output = capsys.readouterr().out
    assert "cs/native/runtime s10" in output
    assert "de/native/runtime s10" in output
    assert "en/native/runtime s10" in output

    assert main(["--json", "dataset", "available"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert {item["language"] for item in payload["available"]} == {"cs", "de", "en"}
    assert {item["schema_version"] for item in payload["available"]} == {"10"}


def test_dataset_human_output_distinguishes_source_variants(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    install_runtime(tmp_path, monkeypatch, "native")
    install_runtime(tmp_path, monkeypatch, "english")

    assert main(["dataset", "list"]) == 0
    output = capsys.readouterr().out
    assert "en/native/runtime" in output
    assert "en/english/runtime" in output
    assert output.count("2026.08.20") == 2
    assert output.count("*") == 1

    assert main(["dataset", "info", "en", "--variant", "runtime"]) == 0
    info = capsys.readouterr().out
    assert "en/native/runtime" in info
    assert "en/english/runtime" in info

    assert main(["--json", "dataset", "info", "en", "--variant", "runtime"]) == 0
    selected_info = json.loads(capsys.readouterr().out)
    assert selected_info["source_variant"] == "english"

    assert main(["--json", "dataset", "list", "--source-variant", "english"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert [item["source_variant"] for item in payload["installed"]] == ["english"]


def test_dataset_download_check_and_update_human_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    install_runtime(tmp_path, monkeypatch, "native")
    item = datasets.list_installed_datasets("en")[0]

    monkeypatch.setattr(cli, "download_dataset", lambda *args, **kwargs: item)
    assert main(["dataset", "download", "en"]) == 0
    assert "Installed en/native/runtime" in capsys.readouterr().out

    monkeypatch.setattr(
        cli,
        "download_dataset",
        lambda *args, **kwargs: item.__class__(
            **{**item.as_dict(), "path": item.path, "already_installed": True}
        ),
    )
    assert main(["dataset", "download", "en"]) == 0
    assert "Already installed en/native/runtime" in capsys.readouterr().out

    status = datasets.DatasetUpdate(
        "en", "runtime", "10", "2026.08.20", "2026.09.01", item.path, True, "native"
    )
    monkeypatch.setattr(cli, "check_dataset_updates", lambda *args, **kwargs: (status,))
    assert main(["dataset", "check", "en"]) == 0
    assert "en/native/runtime 2026.08.20 -> 2026.09.01 update available" in capsys.readouterr().out

    monkeypatch.setattr(cli, "update_datasets", lambda *args, **kwargs: (item,))
    assert main(["dataset", "update", "en"]) == 0
    assert "Updated en/native/runtime" in capsys.readouterr().out


def test_dataset_validate_human_output_and_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    install_runtime(tmp_path, monkeypatch, "english")
    install_runtime(tmp_path, monkeypatch, "native")

    assert main(["dataset", "validate", "en"]) == 0
    output = capsys.readouterr().out.splitlines()
    assert [line.split()[1] for line in output] == ["en/native/runtime", "en/english/runtime"]


def test_dataset_version_aliases_share_destination() -> None:
    parser = _parser()
    for command in ("download", "available", "info", "remove", "validate"):
        if command in {"download", "info", "remove"}:
            args = ["dataset", command, "en"]
        else:
            args = ["dataset", command]
        if command == "remove":
            args.extend(["--variant", "runtime"])
        version_args = parser.parse_args([*args, "--version", "2026.08.20"])
        alias_args = parser.parse_args([*args, "--dataset-version", "2026.08.20"])
        assert version_args.dataset_version == alias_args.dataset_version == "2026.08.20"


def test_parser_help_contract() -> None:
    parser = _parser()

    def visit(current: argparse.ArgumentParser) -> None:
        for action in current._actions:
            if isinstance(action, argparse._SubParsersAction):
                for child in action.choices.values():
                    visit(child)
                continue
            if action.dest == "source_positional":
                assert action.help == argparse.SUPPRESS
                continue
            if action.option_strings:
                assert action.help not in (None, "")
            else:
                assert action.metavar not in (None, "")
                assert action.help not in (None, "")

    visit(parser)
    assert parser.allow_abbrev is False


def test_language_environment_default_is_used(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seen: list[str] = []

    class FakeLexicon:
        def __init__(self, language: str, **kwargs: object) -> None:
            seen.append(language)

        def match_headwords(self, pattern: str, *, syntax: str, limit: int) -> tuple[str, ...]:
            return ()

    monkeypatch.setattr(cli, "Lexicon", FakeLexicon)
    monkeypatch.setenv("LEXHINT_LANGUAGE", "de")
    assert main(["--json", "headwords", "*"]) == 0
    assert seen == ["de"]
    assert json.loads(capsys.readouterr().out)["language"] == "de"

    monkeypatch.setenv("LEXHINT_LANGUAGE", "not-a-language")
    assert main(["headwords", "*"]) == 1
    assert "unsupported Lexhint language" in capsys.readouterr().err
