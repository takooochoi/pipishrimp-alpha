"""Small local durable store for the manual-review boundary.

SQLite is used deliberately as a standard-library, single-node Alpha store.
Only normalized records and audit snapshots are persisted; fetched source
bytes and rejected inputs never enter the database.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Callable

from .ingestion import (
    DEFAULT_ALLOWLIST,
    NormalizedOpportunity,
    OfficialSourceAllowlist,
    ReviewState,
    SourceNotAllowed,
)


class ReviewStoreError(ValueError):
    """Raised when a durable review-store operation is invalid."""


DEFAULT_REVIEW_STORE_PATH = Path(__file__).resolve().parents[1] / ".runtime" / "review.sqlite3"


class ReviewStore:
    """SQLite-backed candidate store with append-only transition audit rows."""

    def __init__(
        self,
        path: str | Path = DEFAULT_REVIEW_STORE_PATH,
        *,
        allowlist: OfficialSourceAllowlist = DEFAULT_ALLOWLIST,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.path = Path(path)
        if str(path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._allowlist = allowlist
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._connection = sqlite3.connect(str(path))
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS review_records (
                stable_id TEXT PRIMARY KEY,
                record_json TEXT NOT NULL,
                review_state TEXT NOT NULL CHECK (
                    review_state IN ('needs_review', 'approved', 'rejected')
                ),
                externally_publishable INTEGER NOT NULL CHECK (
                    externally_publishable IN (0, 1)
                ),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS review_audit (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                stable_id TEXT NOT NULL,
                action TEXT NOT NULL CHECK (
                    action IN ('ingested', 'updated', 'approved', 'rejected')
                ),
                from_state TEXT,
                to_state TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                before_json TEXT,
                after_json TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS review_audit_stable_id_idx
                ON review_audit(stable_id, event_id);
            """
        )
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> ReviewStore:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def add(self, record: NormalizedOpportunity) -> NormalizedOpportunity:
        """Insert a new candidate, always resetting it to manual review."""

        self._validate_record(record)
        pending = self._pending_record(record)
        record_json = self._serialize(pending)
        occurred_at = self._timestamp()
        try:
            with self._connection:
                self._connection.execute(
                    """
                    INSERT INTO review_records (
                        stable_id, record_json, review_state,
                        externally_publishable, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        pending.stable_id,
                        record_json,
                        pending.review_state.value,
                        int(pending.externally_publishable),
                        occurred_at,
                        occurred_at,
                    ),
                )
                self._insert_audit(
                    stable_id=pending.stable_id,
                    action="ingested",
                    from_state=None,
                    to_state=pending.review_state,
                    occurred_at=occurred_at,
                    before_json=None,
                    after_json=record_json,
                )
        except sqlite3.IntegrityError:
            raise ReviewStoreError("duplicate_stable_id") from None
        return pending

    def update_pending(self, record: NormalizedOpportunity) -> NormalizedOpportunity:
        """Explicitly update an unreviewed candidate and record the snapshot."""

        self._validate_record(record)
        current = self.get(record.stable_id)
        if current is None:
            raise ReviewStoreError("record_not_found")
        if current.review_state is not ReviewState.NEEDS_REVIEW:
            raise ReviewStoreError("reviewed_record_update_forbidden")
        if (
            current.source_id != record.source_id
            or current.official_publisher != record.official_publisher
            or str(current.source_url) != str(record.source_url)
        ):
            raise ReviewStoreError("provenance_update_forbidden")

        updated = self._pending_record(record)
        before_json = self._serialize(current)
        after_json = self._serialize(updated)
        occurred_at = self._timestamp()
        with self._connection:
            cursor = self._connection.execute(
                """
                UPDATE review_records
                SET record_json = ?, review_state = ?, externally_publishable = ?, updated_at = ?
                WHERE stable_id = ? AND review_state = 'needs_review'
                """,
                (
                    after_json,
                    updated.review_state.value,
                    int(updated.externally_publishable),
                    occurred_at,
                    updated.stable_id,
                ),
            )
            if cursor.rowcount != 1:
                raise ReviewStoreError("review_state_changed_during_update")
            self._insert_audit(
                stable_id=updated.stable_id,
                action="updated",
                from_state=current.review_state,
                to_state=updated.review_state,
                occurred_at=occurred_at,
                before_json=before_json,
                after_json=after_json,
            )
        return updated

    def get(self, stable_id: str) -> NormalizedOpportunity | None:
        row = self._connection.execute(
            "SELECT * FROM review_records WHERE stable_id = ?",
            (stable_id,),
        ).fetchone()
        return None if row is None else self._deserialize_row(row)

    def list(
        self,
        *,
        state: ReviewState | None = None,
    ) -> tuple[NormalizedOpportunity, ...]:
        if state is None:
            rows = self._connection.execute(
                "SELECT * FROM review_records ORDER BY stable_id"
            ).fetchall()
        else:
            rows = self._connection.execute(
                "SELECT * FROM review_records WHERE review_state = ? ORDER BY stable_id",
                (state.value,),
            ).fetchall()
        return tuple(self._deserialize_row(row) for row in rows)

    def approve(self, stable_id: str) -> NormalizedOpportunity:
        return self._transition(stable_id, ReviewState.APPROVED, "approved")

    def reject(self, stable_id: str) -> NormalizedOpportunity:
        return self._transition(stable_id, ReviewState.REJECTED, "rejected")

    def audit_log(self, stable_id: str) -> tuple[dict[str, object], ...]:
        rows = self._connection.execute(
            "SELECT * FROM review_audit WHERE stable_id = ? ORDER BY event_id",
            (stable_id,),
        ).fetchall()
        return tuple(
            {
                "event_id": row["event_id"],
                "stable_id": row["stable_id"],
                "action": row["action"],
                "from_state": row["from_state"],
                "to_state": row["to_state"],
                "occurred_at": row["occurred_at"],
                "before": None
                if row["before_json"] is None
                else json.loads(row["before_json"]),
                "after": json.loads(row["after_json"]),
            }
            for row in rows
        )

    def _transition(
        self,
        stable_id: str,
        state: ReviewState,
        action: str,
    ) -> NormalizedOpportunity:
        current = self.get(stable_id)
        if current is None:
            raise ReviewStoreError("record_not_found")
        if current.review_state is not ReviewState.NEEDS_REVIEW:
            raise ReviewStoreError("record_already_reviewed")

        updated = NormalizedOpportunity.model_validate(
            current.model_dump(mode="python")
            | {
                "review_state": state,
                "externally_publishable": state is ReviewState.APPROVED,
            }
        )
        before_json = self._serialize(current)
        after_json = self._serialize(updated)
        occurred_at = self._timestamp()
        with self._connection:
            cursor = self._connection.execute(
                """
                UPDATE review_records
                SET record_json = ?, review_state = ?, externally_publishable = ?, updated_at = ?
                WHERE stable_id = ? AND review_state = 'needs_review'
                """,
                (
                    after_json,
                    updated.review_state.value,
                    int(updated.externally_publishable),
                    occurred_at,
                    stable_id,
                ),
            )
            if cursor.rowcount != 1:
                raise ReviewStoreError("review_state_changed_during_transition")
            self._insert_audit(
                stable_id=stable_id,
                action=action,
                from_state=current.review_state,
                to_state=updated.review_state,
                occurred_at=occurred_at,
                before_json=before_json,
                after_json=after_json,
            )
        return updated

    def _validate_record(self, record: NormalizedOpportunity) -> None:
        try:
            source = self._allowlist.resolve(str(record.source_url))
        except SourceNotAllowed:
            raise ReviewStoreError("record_source_not_allowed") from None
        if record.source_id != source.source_id or record.official_publisher != source.publisher:
            raise ReviewStoreError("record_provenance_invalid")

    @staticmethod
    def _pending_record(record: NormalizedOpportunity) -> NormalizedOpportunity:
        return NormalizedOpportunity.model_validate(
            record.model_dump(mode="python")
            | {
                "review_state": ReviewState.NEEDS_REVIEW,
                "externally_publishable": False,
            }
        )

    @staticmethod
    def _serialize(record: NormalizedOpportunity) -> str:
        return json.dumps(
            record.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    @staticmethod
    def _deserialize_row(row: sqlite3.Row) -> NormalizedOpportunity:
        try:
            data = json.loads(row["record_json"])
            deadline = data.get("deadline")
            if (
                isinstance(deadline, dict)
                and deadline.get("precision") == "date"
                and isinstance(deadline.get("value"), str)
            ):
                deadline["value"] = date.fromisoformat(deadline["value"])
            record = NormalizedOpportunity.model_validate(data)
        except (AttributeError, TypeError, ValueError, json.JSONDecodeError):
            raise ReviewStoreError("stored_record_invalid") from None
        if (
            record.review_state.value != row["review_state"]
            or int(record.externally_publishable) != row["externally_publishable"]
        ):
            raise ReviewStoreError("stored_review_state_inconsistent")
        return record

    def _timestamp(self) -> str:
        current = self._clock()
        if current.tzinfo is None or current.utcoffset() is None:
            raise ReviewStoreError("store_clock_must_include_timezone")
        return current.astimezone(timezone.utc).isoformat()

    def _insert_audit(
        self,
        *,
        stable_id: str,
        action: str,
        from_state: ReviewState | None,
        to_state: ReviewState,
        occurred_at: str,
        before_json: str | None,
        after_json: str,
    ) -> None:
        self._connection.execute(
            """
            INSERT INTO review_audit (
                stable_id, action, from_state, to_state,
                occurred_at, before_json, after_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                stable_id,
                action,
                None if from_state is None else from_state.value,
                to_state.value,
                occurred_at,
                before_json,
                after_json,
            ),
        )
