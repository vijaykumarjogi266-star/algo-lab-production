"""Algo Lab Unit Tests for Restored Modules: Evidence Framework, Credential Store, and Forward Gate Tracker."""

import os
import json
import tempfile
import pytest
from datetime import datetime, timezone

from collectors.evidence_framework import (
    canonical_json_serialize,
    compute_evidence_hash,
    EvidenceIntegrityError,
)
from collectors.secure_credential_store import SecureCredentialStore
from paper.forward_gate_tracker import ForwardGateTracker, ForwardSessionState


def test_canonical_json_serialize():
    data = {"b": 2, "a": 1, "record_hash": "should_be_ignored"}
    serialized = canonical_json_serialize(data)
    assert serialized == '{"a":1,"b":2}'


def test_compute_evidence_hash():
    data1 = {"a": 1, "b": 2}
    data2 = {"b": 2, "a": 1}
    h1 = compute_evidence_hash(data1)
    h2 = compute_evidence_hash(data2)
    assert h1 == h2
    assert len(h1) == 64


def test_secure_credential_store_in_memory(tmp_path):
    key_file = tmp_path / "master.key"
    store_file = tmp_path / "credentials.enc"
    
    store = SecureCredentialStore(key_path=str(key_file), store_path=str(store_file))
    assert store.master_key is not None
    assert len(store.master_key) == 32


def test_forward_gate_tracker_evaluation(tmp_path):
    log_dir = tmp_path / "logs"
    tracker = ForwardGateTracker(log_dir=str(log_dir))

    # Evaluate empty gate history
    res = tracker.evaluate_forward_gate()
    assert res["gate_status"] == "INCOMPLETE"
    assert res["valid_trading_sessions"] == 0

    # Record historical/synthetic session -> must be EXCLUDED
    rec1 = tracker.record_session_observation(
        session_id="SESH-001",
        session_date="2026-09-01",
        status=ForwardSessionState.SESSION_PAPER_COMPLETE,
        is_synthetic=True,
    )
    assert rec1["state"] == ForwardSessionState.SESSION_EXCLUDED.value

    # Record genuine valid sessions
    tracker.record_session_observation(
        session_id="SESH-002",
        session_date="2026-09-02",
        status=ForwardSessionState.SESSION_PAPER_COMPLETE,
        is_synthetic=False,
    )
    
    res2 = tracker.evaluate_forward_gate()
    assert res2["gate_status"] == "INCOMPLETE"
    assert res2["valid_trading_sessions"] == 1
    assert res2["excluded_sessions_count"] == 1
