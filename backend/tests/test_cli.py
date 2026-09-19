import json
from datetime import datetime, timezone
from pathlib import Path

import app.cli as cli
from app.ingestion import FetchedSource
from app.source_adapters import BuilderGrantsSourceAdapter, ClockInSourceAdapter


FIXTURES = Path(__file__).parent / "fixtures"
RETRIEVED_AT = datetime(2026, 9, 18, 12, 5, tzinfo=timezone.utc)


class FixtureFetcher:
    def __init__(self, **kwargs) -> None:
        del kwargs

    def fetch(self, url: str) -> FetchedSource:
        adapters = (ClockInSourceAdapter(), BuilderGrantsSourceAdapter())
        for adapter in adapters:
            if url == adapter.source_url:
                fixture = "clock_in.html" if adapter.name == "clock-in" else "builder_grants.html"
                return FetchedSource(
                    source_id=adapter.source_id,
                    publisher=adapter.publisher,
                    url=adapter.source_url,
                    retrieved_at=RETRIEVED_AT,
                    content_type="text/html",
                    body=(FIXTURES / fixture).read_bytes(),
                )
        raise AssertionError("unexpected source URL")


def test_cli_ingest_list_inspect_and_review_without_publication(tmp_path, monkeypatch, capsys) -> None:
    db_path = tmp_path / "review.sqlite3"
    monkeypatch.setattr(cli, "BoundedOfficialSourceFetcher", FixtureFetcher)

    assert cli.main(["--db", str(db_path), "ingest"]) == 0
    ingested = json.loads(capsys.readouterr().out)
    assert [item["status"] for item in ingested["outcomes"]] == ["stored", "stored"]
    assert all(
        item["fetch"]["http_success"] is True
        and item["fetch"]["content_type"] == "text/html"
        for item in ingested["outcomes"]
    )
    assert all(
        item["record"]["review_state"] == "needs_review"
        and item["record"]["externally_publishable"] is False
        for item in ingested["outcomes"]
    )

    assert cli.main(["--db", str(db_path), "list", "--state", "needs_review"]) == 0
    pending = json.loads(capsys.readouterr().out)
    assert [item["stable_id"] for item in pending["records"]] == [
        "solana-mobile-builder-grants",
        "solana-mobile-clock-in-hackathon",
    ]

    assert cli.main(["--db", str(db_path), "approve", "solana-mobile-clock-in-hackathon"]) == 0
    approved = json.loads(capsys.readouterr().out)["record"]
    assert approved["review_state"] == "approved"
    assert approved["externally_publishable"] is True

    assert cli.main(["--db", str(db_path), "reject", "solana-mobile-builder-grants"]) == 0
    rejected = json.loads(capsys.readouterr().out)["record"]
    assert rejected["review_state"] == "rejected"
    assert rejected["externally_publishable"] is False

    assert cli.main(["--db", str(db_path), "show", "solana-mobile-clock-in-hackathon"]) == 0
    shown = json.loads(capsys.readouterr().out)["record"]
    assert shown["source_url"] == ClockInSourceAdapter().source_url

    assert cli.main(["--db", str(db_path), "audit", "solana-mobile-clock-in-hackathon"]) == 0
    audit = json.loads(capsys.readouterr().out)["events"]
    assert [event["action"] for event in audit] == ["ingested", "approved"]


def test_cli_requires_explicit_update_for_duplicate_ingestion(tmp_path, monkeypatch, capsys) -> None:
    db_path = tmp_path / "review.sqlite3"
    monkeypatch.setattr(cli, "BoundedOfficialSourceFetcher", FixtureFetcher)

    assert cli.main(["--db", str(db_path), "ingest", "--source", "clock-in"]) == 0
    capsys.readouterr()
    assert (
        cli.main(["--db", str(db_path), "ingest", "--source", "clock-in"]) == 1
    )
    duplicate = json.loads(capsys.readouterr().out)
    assert duplicate["outcomes"][0]["code"] == "duplicate_stable_id"

    assert (
        cli.main(
            [
                "--db",
                str(db_path),
                "ingest",
                "--source",
                "clock-in",
                "--update-pending",
            ]
        )
        == 0
    )
    updated = json.loads(capsys.readouterr().out)
    assert updated["outcomes"][0]["status"] == "stored"
