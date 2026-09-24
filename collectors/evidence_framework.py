"""
Algo Lab Stage 26 Phase 26A — Baseline & Evidence Lock Framework

Provides immutable, tamper-evident, append-only evidence recording for forward market data
and paper trading execution evidence.

Key Requirements:
1. Immutable/append-only evidence records and manifests.
2. Complete metadata tracking: evidence_id, run_id, source_id, collection_timestamp,
   session_date, software_identity (git commit/version), configuration_hash, data_file_hashes,
   provenance_metadata, quality_status, qualification_status (VALID/INVALID), failure_reasons,
   is_synthetic, is_replayed.
3. Fail-closed behavior: never allow a failed collection to be silently represented as VALID.
4. SHA-256 hash chaining across evidence ledger entries (previous_record_hash -> record_hash).
"""

import os
import sys
import json
import hashlib
import tempfile
import subprocess
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

EVIDENCE_BASE_DIR = "/root/sandbox/algolab-data-lab/data/evidence"
EVIDENCE_MANIFESTS_DIR = os.path.join(EVIDENCE_BASE_DIR, "manifests")
EVIDENCE_RECORDS_DIR = os.path.join(EVIDENCE_BASE_DIR, "records")
GENESIS_HASH = "GENESIS_EVIDENCE_" + "0" * 48


class EvidenceIntegrityError(Exception):
    """Raised when evidence verification, serialization, or hash-chain integrity fails."""

    pass


def canonical_json_serialize(data_dict: dict) -> str:
    """
    Produces deterministic, canonical JSON serialization of a dictionary.
    Keys are sorted alphabetically, un-needed whitespace is removed, and record_hash is omitted.
    """
    if not isinstance(data_dict, dict):
        raise EvidenceIntegrityError("Evidence data must be a dictionary.")

    clean_dict = {k: v for k, v in data_dict.items() if k != "record_hash"}
    try:
        return json.dumps(clean_dict, sort_keys=True, separators=(",", ":"))
    except Exception as e:
        raise EvidenceIntegrityError(f"Canonical JSON serialization failed: {e}")


def compute_evidence_hash(data_dict: dict) -> str:
    """Computes SHA-256 digest of canonical JSON serialized evidence payload."""
    serialized = canonical_json_serialize(data_dict)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def get_software_identity() -> Dict[str, str]:
    """Retrieves current software identity metadata including git commit hash."""
    software_id = {
        "version": "26A.1",
        "git_commit": "UNKNOWN",
        "python_version": sys.version.split()[0],
        "environment": "algolab-data-lab",
    }
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd="/root/sandbox/algolab-data-lab",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5,
        )
        if res.returncode == 0 and res.stdout.strip():
            software_id["git_commit"] = res.stdout.strip()
    except Exception:
        pass
    return software_id


class EvidenceFramework:
    """Manages append-only, tamper-evident evidence collection and ledger verification."""

    def __init__(
        self,
        base_dir: str = EVIDENCE_BASE_DIR,
        manifests_dir: Optional[str] = None,
        records_dir: Optional[str] = None,
    ):
        self.base_dir = base_dir
        self.manifests_dir = manifests_dir or os.path.join(self.base_dir, "manifests")
        self.records_dir = records_dir or os.path.join(self.base_dir, "records")

        os.makedirs(self.manifests_dir, exist_ok=True)
        os.makedirs(self.records_dir, exist_ok=True)
        self.ledger_file = os.path.join(self.manifests_dir, "evidence_ledger.jsonl")

    def _get_latest_ledger_hash(self) -> str:
        """Returns the hash of the last record in the ledger, or GENESIS_HASH if empty."""
        records = self.load_evidence_ledger(verify_chain=False)
        if not records:
            return GENESIS_HASH
        return records[-1]["record_hash"]

    def create_evidence_record(
        self,
        run_id: str,
        source_id: str,
        session_date: str,
        data_file_hashes: Dict[str, str],
        quality_status: str = "QUALITY_PASSED",
        qualification_status: str = "VALID",
        failure_reasons: Optional[List[str]] = None,
        provenance_metadata: Optional[Dict[str, Any]] = None,
        configuration_hash: Optional[str] = None,
        is_synthetic: bool = False,
        is_replayed: bool = False,
        collection_timestamp: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Creates and persists an immutable evidence record.
        Strict fail-closed enforcement: if quality_status is FAILED or failure_reasons exist,
        qualification_status MUST be INVALID.
        """
        reasons = failure_reasons or []
        if quality_status != "QUALITY_PASSED" or len(reasons) > 0:
            qualification_status = "INVALID"

        now_utc = collection_timestamp or datetime.now(timezone.utc).isoformat()
        prev_hash = self._get_latest_ledger_hash()

        # Deterministic evidence ID based on run_id, source_id, session_date, and timestamp
        raw_id_str = f"{run_id}:{source_id}:{session_date}:{now_utc}"
        evidence_id = "ev_" + hashlib.sha256(raw_id_str.encode("utf-8")).hexdigest()[:16]

        record = {
            "evidence_id": evidence_id,
            "run_id": run_id,
            "source_id": source_id,
            "session_date": session_date,
            "collection_timestamp": now_utc,
            "software_identity": get_software_identity(),
            "configuration_hash": configuration_hash or hashlib.sha256(b"default_config").hexdigest(),
            "data_file_hashes": data_file_hashes,
            "provenance_metadata": provenance_metadata or {},
            "quality_status": quality_status,
            "qualification_status": qualification_status,
            "failure_reasons": reasons,
            "is_synthetic": is_synthetic,
            "is_replayed": is_replayed,
            "previous_record_hash": prev_hash,
        }

        # Calculate self hash
        record_hash = compute_evidence_hash(record)
        record["record_hash"] = record_hash

        # Persist record JSON file atomically
        date_records_dir = os.path.join(self.records_dir, session_date)
        os.makedirs(date_records_dir, exist_ok=True)
        record_file = os.path.join(date_records_dir, f"{evidence_id}.json")

        self._atomic_write_json(record_file, record)

        # Append to master ledger JSONL atomically
        self._append_to_ledger(record)

        return record

    def _atomic_write_json(self, file_path: str, data: dict):
        """Writes dictionary to file atomically using mkstemp + os.replace."""
        target_dir = os.path.dirname(file_path)
        os.makedirs(target_dir, exist_ok=True)

        fd, tmp_path = tempfile.mkstemp(dir=target_dir, prefix=".tmp_ev_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, sort_keys=True)
            os.replace(tmp_path, file_path)
        except Exception as e:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise EvidenceIntegrityError(f"Atomic file write failed for {file_path}: {e}")

    def _append_to_ledger(self, record: dict):
        """Appends record to evidence_ledger.jsonl atomically."""
        line = json.dumps(record, sort_keys=True) + "\n"
        try:
            with open(self.ledger_file, "a", encoding="utf-8") as f:
                f.write(line)
        except Exception as e:
            raise EvidenceIntegrityError(f"Failed to append record to evidence ledger: {e}")

    def load_evidence_ledger(self, verify_chain: bool = True) -> List[Dict[str, Any]]:
        """Loads all evidence records from the ledger file, optionally verifying hash chain."""
        records = []
        if not os.path.exists(self.ledger_file):
            return []

        try:
            with open(self.ledger_file, "r", encoding="utf-8") as f:
                for line_no, line in enumerate(f, 1):
                    line = line.strip()
                    if line:
                        try:
                            rec = json.loads(line)
                            records.append(rec)
                        except Exception as e:
                            raise EvidenceIntegrityError(
                                f"Corrupt line {line_no} in evidence ledger '{self.ledger_file}': {e}"
                            )
        except Exception as e:
            if isinstance(e, EvidenceIntegrityError):
                raise
            raise EvidenceIntegrityError(f"Failed to read evidence ledger: {e}")

        if verify_chain and records:
            self.verify_evidence_chain(records)

        return records

    def verify_evidence_chain(self, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Validates hash chain integrity and canonical SHA-256 hashes of all evidence records.
        Fails closed with EvidenceIntegrityError if any record is corrupt or tampered.
        """
        if not records:
            return {"valid": True, "record_count": 0}

        expected_prev_hash = GENESIS_HASH

        for i, rec in enumerate(records):
            # Check previous_record_hash
            prev_hash = rec.get("previous_record_hash")
            if prev_hash != expected_prev_hash:
                raise EvidenceIntegrityError(
                    f"Evidence hash chain broken at record index {i} ({rec.get('evidence_id')}): "
                    f"expected previous '{expected_prev_hash}', got '{prev_hash}'"
                )

            # Check self hash
            actual_hash = compute_evidence_hash(rec)
            stored_hash = rec.get("record_hash")
            if stored_hash != actual_hash:
                raise EvidenceIntegrityError(
                    f"Evidence record tampering detected at index {i} ({rec.get('evidence_id')}): "
                    f"stored hash '{stored_hash}', calculated hash '{actual_hash}'"
                )

            # Check qualification fail-closed rule
            if rec.get("quality_status") != "QUALITY_PASSED" or len(rec.get("failure_reasons", [])) > 0:
                if rec.get("qualification_status") == "VALID":
                    raise EvidenceIntegrityError(
                        f"Fail-closed breach at record index {i} ({rec.get('evidence_id')}): "
                        f"record has quality/failure errors but qualification_status is VALID."
                    )

            expected_prev_hash = stored_hash

        return {"valid": True, "record_count": len(records), "latest_hash": expected_prev_hash}
