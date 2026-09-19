"""Local operator commands for bounded ingestion and manual review."""

from __future__ import annotations

import argparse
from pathlib import Path
import json
from typing import Sequence

from .ingestion import (
    BoundedOfficialSourceFetcher,
    ReviewState,
    SourceFetchRejected,
    SourceNotAllowed,
)
from .review_store import (
    DEFAULT_REVIEW_STORE_PATH,
    ReviewStore,
    ReviewStoreError,
)
from .source_adapters import (
    INITIAL_SOURCE_ADAPTERS,
    INITIAL_SOURCE_FETCH_POLICY,
    SourceAdapterError,
    adapter_by_name,
)


def _json_value(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)


def _record_value(record: object) -> object:
    return record.model_dump(mode="json")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli",
        description="Bounded local official-source ingestion and manual review.",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_REVIEW_STORE_PATH,
        help="SQLite review-store path (default: backend/.runtime/review.sqlite3)",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    ingest = commands.add_parser("ingest", help="fetch and ingest configured official sources")
    ingest.add_argument(
        "--source",
        choices=("all", "clock-in", "builder-grants"),
        default="all",
    )
    ingest.add_argument(
        "--update-pending",
        action="store_true",
        help="explicitly update an existing needs_review candidate",
    )

    list_command = commands.add_parser("list", help="list stored candidates")
    list_command.add_argument(
        "--state",
        choices=tuple(state.value for state in ReviewState),
    )

    show = commands.add_parser("show", help="show one normalized candidate")
    show.add_argument("stable_id")

    approve = commands.add_parser("approve", help="explicitly approve one candidate")
    approve.add_argument("stable_id")

    reject = commands.add_parser("reject", help="explicitly reject one candidate")
    reject.add_argument("stable_id")

    audit = commands.add_parser("audit", help="show append-only audit events")
    audit.add_argument("stable_id")
    return parser


def _selected_adapters(name: str):
    if name == "all":
        return INITIAL_SOURCE_ADAPTERS
    return (adapter_by_name(name),)


def _ingest(args: argparse.Namespace) -> int:
    outcomes: list[dict[str, object]] = []
    fetcher = BoundedOfficialSourceFetcher(policy=INITIAL_SOURCE_FETCH_POLICY)
    with ReviewStore(args.db) as store:
        for adapter in _selected_adapters(args.source):
            try:
                fetched = fetcher.fetch(adapter.source_url)
                record = adapter.parse(fetched)
                persisted = (
                    store.update_pending(record)
                    if args.update_pending
                    else store.add(record)
                )
            except (
                SourceAdapterError,
                SourceFetchRejected,
                SourceNotAllowed,
                ReviewStoreError,
            ) as exc:
                outcomes.append(
                    {
                        "adapter": adapter.name,
                        "status": "error",
                        "code": str(exc),
                    }
                )
                continue
            outcomes.append(
                {
                    "adapter": adapter.name,
                    "status": "stored",
                    "fetch": {
                        "source_url": fetched.url,
                        "http_success": True,
                        "content_type": fetched.content_type,
                    },
                    "record": _record_value(persisted),
                }
            )
    print(_json_value({"outcomes": outcomes}))
    return 0 if all(item["status"] == "stored" for item in outcomes) else 1


def _review_command(args: argparse.Namespace) -> int:
    with ReviewStore(args.db) as store:
        if args.command == "list":
            state = None if args.state is None else ReviewState(args.state)
            result = {"records": [_record_value(record) for record in store.list(state=state)]}
        elif args.command == "show":
            record = store.get(args.stable_id)
            if record is None:
                print(_json_value({"status": "error", "code": "record_not_found"}))
                return 1
            result = {"record": _record_value(record)}
        elif args.command == "audit":
            result = {"events": store.audit_log(args.stable_id)}
        elif args.command == "approve":
            result = {"record": _record_value(store.approve(args.stable_id))}
        elif args.command == "reject":
            result = {"record": _record_value(store.reject(args.stable_id))}
        else:
            raise ReviewStoreError("command_not_supported")
    print(_json_value(result))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "ingest":
            return _ingest(args)
        return _review_command(args)
    except ReviewStoreError as exc:
        print(_json_value({"status": "error", "code": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
