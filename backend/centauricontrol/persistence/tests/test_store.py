"""
Tests for centauricontrol.persistence.store.DataStore.

Run with:  pytest backend/centauricontrol/persistence/tests/test_store.py
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from centauricontrol.persistence.store import DataStore


# ---------------------------------------------------------------------------
# read()
# ---------------------------------------------------------------------------

class TestRead:
    def test_returns_none_for_missing_file(self, tmp_path: Path) -> None:
        store = DataStore(tmp_path)
        assert store.read("nonexistent.json") is None

    def test_returns_dict_for_existing_file(self, tmp_path: Path) -> None:
        store = DataStore(tmp_path)
        store.write("data.json", {"key": "value"})
        result = store.read("data.json")
        assert result == {"key": "value"}

    def test_returns_list_for_array_file(self, tmp_path: Path) -> None:
        store = DataStore(tmp_path)
        store.write("arr.json", [1, 2, 3])
        assert store.read("arr.json") == [1, 2, 3]


# ---------------------------------------------------------------------------
# write()
# ---------------------------------------------------------------------------

class TestWrite:
    def test_creates_file_with_correct_content(self, tmp_path: Path) -> None:
        store = DataStore(tmp_path)
        payload = {"printer": "Centauri Carbon", "port": 3030}
        store.write("printers.json", payload)

        raw = (tmp_path / "printers.json").read_text(encoding="utf-8")
        assert json.loads(raw) == payload

    def test_overwrites_existing_file(self, tmp_path: Path) -> None:
        store = DataStore(tmp_path)
        store.write("cfg.json", {"v": 1})
        store.write("cfg.json", {"v": 2})
        assert store.read("cfg.json") == {"v": 2}

    def test_atomic_tmp_file_is_cleaned_up(self, tmp_path: Path) -> None:
        """After a successful write the .tmp file must not remain."""
        store = DataStore(tmp_path)
        store.write("x.json", {"a": 1})
        assert not (tmp_path / "x.json.tmp").exists()

    def test_atomic_original_survives_if_only_tmp_exists(self, tmp_path: Path) -> None:
        """Simulate a crash after .tmp is written but before os.replace().

        The original file must still be intact; the stale .tmp is ignored by
        the DataStore (it never reads .tmp files directly).
        """
        store = DataStore(tmp_path)
        original_data = {"stable": True}
        store.write("safe.json", original_data)

        # Simulate a crashed write: only the .tmp file is present
        # (the replace never happened).
        stale_tmp = tmp_path / "safe.json.tmp"
        stale_tmp.write_text(json.dumps({"corrupt": True}), encoding="utf-8")

        # The original file still contains the previous good data.
        result = store.read("safe.json")
        assert result == original_data

    def test_unicode_preserved(self, tmp_path: Path) -> None:
        store = DataStore(tmp_path)
        store.write("u.json", {"name": "日本語テスト"})
        assert store.read("u.json") == {"name": "日本語テスト"}


# ---------------------------------------------------------------------------
# append_json_array()
# ---------------------------------------------------------------------------

class TestAppendJsonArray:
    def test_creates_array_when_file_missing(self, tmp_path: Path) -> None:
        store = DataStore(tmp_path)
        store.append_json_array("history.json", {"entry": 1})
        assert store.read("history.json") == [{"entry": 1}]

    def test_appends_to_existing_array(self, tmp_path: Path) -> None:
        store = DataStore(tmp_path)
        store.write("history.json", [{"entry": 1}])
        store.append_json_array("history.json", {"entry": 2})
        assert store.read("history.json") == [{"entry": 1}, {"entry": 2}]

    def test_does_not_lose_previous_data(self, tmp_path: Path) -> None:
        store = DataStore(tmp_path)
        for i in range(10):
            store.append_json_array("log.json", {"i": i})
        result = store.read("log.json")
        assert isinstance(result, list)
        assert len(result) == 10
        assert result[0] == {"i": 0}
        assert result[-1] == {"i": 9}

    def test_recovers_if_existing_content_is_not_list(self, tmp_path: Path) -> None:
        """If the file somehow contains a non-array, start fresh."""
        store = DataStore(tmp_path)
        store.write("bad.json", {"not": "a list"})
        store.append_json_array("bad.json", {"new": "item"})
        assert store.read("bad.json") == [{"new": "item"}]


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------

class TestConcurrency:
    def test_concurrent_appends_do_not_corrupt_data(self, tmp_path: Path) -> None:
        """Multiple threads appending to the same file must not lose items."""
        store = DataStore(tmp_path)
        n_threads = 20
        items_per_thread = 10

        def worker(thread_id: int) -> None:
            for i in range(items_per_thread):
                store.append_json_array("concurrent.json", {"t": thread_id, "i": i})

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        result = store.read("concurrent.json")
        assert isinstance(result, list)
        assert len(result) == n_threads * items_per_thread

    def test_concurrent_writes_do_not_corrupt_data(self, tmp_path: Path) -> None:
        """Concurrent write() calls must each produce a valid JSON file."""
        store = DataStore(tmp_path)
        errors: list[Exception] = []

        def worker(i: int) -> None:
            try:
                store.write("shared.json", {"value": i})
            except Exception as exc:  # pragma: no cover
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        # Whatever the last writer wrote must be valid JSON.
        result = store.read("shared.json")
        assert isinstance(result, dict)
        assert "value" in result
