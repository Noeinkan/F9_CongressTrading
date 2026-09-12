"""High-water mark and cluster de-duplication."""
from __future__ import annotations

from src.db import get_connection
from src.notify import state as notify_state


def _conn():
    conn = get_connection()
    notify_state.init_notify_state(conn)
    return conn


def test_state_roundtrip_and_defaults():
    conn = _conn()
    try:
        assert notify_state.last_transaction_id(conn) == 0
        notify_state.set_last_transaction_id(conn, 4321)
        assert notify_state.last_transaction_id(conn) == 4321
        assert notify_state.get_state(conn, "missing", "fallback") == "fallback"
        assert notify_state.get_int_state(conn, "missing", 7) == 7
    finally:
        conn.close()


def test_non_numeric_state_falls_back_instead_of_raising():
    conn = _conn()
    try:
        notify_state.set_state(conn, notify_state.LAST_TRANSACTION_ID, "garbage")
        assert notify_state.last_transaction_id(conn) == 0
    finally:
        conn.close()


def test_bootstrap_flag_is_separate_from_the_mark():
    conn = _conn()
    try:
        assert not notify_state.is_bootstrapped(conn)
        notify_state.mark_bootstrapped(conn, 99)
        assert notify_state.is_bootstrapped(conn)
        assert notify_state.last_transaction_id(conn) == 99
    finally:
        conn.close()


def test_cluster_is_new_only_until_reported_and_again_when_it_grows():
    conn = _conn()
    try:
        key = "cluster:NVDA:Coordinated buy"
        assert notify_state.cluster_is_new(conn, key, 3)

        notify_state.record_cluster(conn, key, 3)
        assert not notify_state.cluster_is_new(conn, key, 3), "same size is not news"
        assert not notify_state.cluster_is_new(conn, key, 2)

        assert notify_state.cluster_is_new(conn, key, 5), "a grown cluster is news"
        notify_state.record_cluster(conn, key, 5)
        assert not notify_state.cluster_is_new(conn, key, 5)
    finally:
        conn.close()


def test_event_run_records_the_last_error():
    conn = _conn()
    try:
        notify_state.record_event_run(conn, error="HTTP 401: Unauthorized")
        assert "401" in notify_state.get_state(conn, notify_state.LAST_DELIVERY_ERROR)
        notify_state.record_event_run(conn)
        assert notify_state.get_state(conn, notify_state.LAST_DELIVERY_ERROR) == ""
    finally:
        conn.close()


def test_digest_date_roundtrip():
    conn = _conn()
    try:
        assert notify_state.last_digest_date(conn) == ""
        notify_state.set_last_digest_date(conn, "2026-09-07")
        assert notify_state.last_digest_date(conn) == "2026-09-07"
    finally:
        conn.close()
