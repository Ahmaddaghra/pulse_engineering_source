"""Independent read-only invariant audit. Does not import the ingestion implementation."""

import hashlib
import json
import os
from pathlib import Path

import psycopg


def main() -> None:
    dsn = os.environ["PULSE_DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://", 1)
    root = Path(os.environ.get("PULSE_OBJECT_ROOT", "artifacts")).resolve()
    findings: list[str] = []
    counts: dict[str, int] = {}
    with psycopg.connect(dsn) as connection, connection.cursor() as cursor:
        for table in (
            "fetch_attempts",
            "fetch_receipts",
            "outbox",
            "publication_occurrences",
            "article_revisions",
            "feed_item_observations",
            "snapshots",
        ):
            # Names above are fixed program literals, not user-controlled identifiers.
            cursor.execute(f"SELECT count(*) FROM {table}")
            counts[table] = cursor.fetchone()[0]
        cursor.execute("""
            SELECT r.id FROM fetch_receipts r LEFT JOIN outbox o
              ON o.receipt_id=r.id AND o.topic='parse_requested'
            WHERE o.id IS NULL
        """)
        findings.extend(f"receipt has no parse event: {row[0]}" for row in cursor)
        cursor.execute("""
            SELECT o.id FROM feed_item_observations o JOIN fetch_receipts r ON r.id=o.receipt_id
              JOIN article_revisions v ON v.id=o.revision_id
            WHERE o.occurrence_id != v.occurrence_id OR o.source_id != r.source_id
              OR o.received_at != r.received_at
        """)
        findings.extend(f"observation provenance mismatch: {row[0]}" for row in cursor)
        cursor.execute("SELECT id, fields, fingerprint FROM article_revisions")
        for revision_id, fields, expected in cursor:
            encoded = json.dumps(
                fields, sort_keys=True, ensure_ascii=False, separators=(",", ":")
            ).encode()
            if hashlib.sha256(encoded).hexdigest() != expected:
                findings.append(f"revision fingerprint mismatch: {revision_id}")
        cursor.execute("SELECT id, manifest, sha256 FROM snapshots")
        for snapshot_id, manifest, expected in cursor:
            if hashlib.sha256(manifest.encode()).hexdigest() != expected:
                findings.append(f"manifest hash mismatch: {snapshot_id}")
        cursor.execute("""
            SELECT a.key, a.sha256 FROM artifacts a JOIN source_policies p ON p.id=a.policy_id
              JOIN sources s ON s.current_policy_id=p.id
            WHERE p.state='APPROVED' AND p.expires_at > clock_timestamp()
              AND a.expires_at > clock_timestamp()
        """)
        for key, expected in cursor:
            candidate = (root / key).resolve()
            if not candidate.is_relative_to(root):
                findings.append(f"object escaped root: {key}")
                continue
            try:
                with candidate.open("rb") as artifact:
                    data = artifact.read(4194305)
                if len(data) > 4194304 or hashlib.sha256(data).hexdigest() != expected:
                    findings.append(f"object hash/size mismatch: {key}")
            except OSError:
                findings.append(f"object unavailable: {key}")
    print(
        json.dumps(
            {"status": "PASS" if not findings else "FAIL", "counts": counts, "findings": findings},
            indent=2,
        )
    )
    if findings:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
