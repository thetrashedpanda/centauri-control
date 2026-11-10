"""
Tests for centauricontrol.printers.sdcp pure functions.

Run with:  pytest backend/centauricontrol/printers/tests/test_sdcp.py
"""

from __future__ import annotations

import json
import math

import pytest

from centauricontrol.printers.sdcp import (
    CMD_ATTRS,
    CMD_CAMERA,
    CMD_DELETE_FILES,
    CMD_HISTORY_DETAIL,
    CMD_HISTORY_LIST,
    CMD_LIGHT,
    CMD_LIST_FILES,
    CMD_PAUSE,
    CMD_RESUME,
    CMD_SET_NAME,
    CMD_SET_RUNTIME,
    CMD_SKIP_PREHEAT,
    CMD_START,
    CMD_STATUS,
    CMD_STOP,
    CMD_STOP_FEED,
    CMD_TIMELAPSE,
    MACHINE_STATUS,
    PRINT_STATUS,
    _deep_merge,
    decode_printinfo,
    filament_mm_to_grams,
    make_msg,
)


# ---------------------------------------------------------------------------
# CMD_* constants sanity check
# ---------------------------------------------------------------------------

class TestCommandConstants:
    def test_status_is_zero(self) -> None:
        assert CMD_STATUS == 0

    def test_attrs_is_one(self) -> None:
        assert CMD_ATTRS == 1

    def test_start_is_128(self) -> None:
        assert CMD_START == 128

    def test_pause_is_129(self) -> None:
        assert CMD_PAUSE == 129

    def test_stop_is_130(self) -> None:
        assert CMD_STOP == 130

    def test_resume_is_131(self) -> None:
        assert CMD_RESUME == 131

    def test_stop_feed_is_132(self) -> None:
        assert CMD_STOP_FEED == 132

    def test_skip_preheat_is_133(self) -> None:
        assert CMD_SKIP_PREHEAT == 133

    def test_set_name_is_192(self) -> None:
        assert CMD_SET_NAME == 192

    def test_list_files_is_258(self) -> None:
        assert CMD_LIST_FILES == 258

    def test_delete_files_is_259(self) -> None:
        assert CMD_DELETE_FILES == 259

    def test_history_list_is_320(self) -> None:
        assert CMD_HISTORY_LIST == 320

    def test_history_detail_is_321(self) -> None:
        assert CMD_HISTORY_DETAIL == 321

    def test_camera_is_386(self) -> None:
        assert CMD_CAMERA == 386

    def test_timelapse_is_387(self) -> None:
        assert CMD_TIMELAPSE == 387

    def test_light_is_403(self) -> None:
        assert CMD_LIGHT == 403

    def test_set_runtime_is_403(self) -> None:
        assert CMD_SET_RUNTIME == 403


# ---------------------------------------------------------------------------
# PRINT_STATUS
# ---------------------------------------------------------------------------

class TestPrintStatus:
    def test_contains_idle(self) -> None:
        assert PRINT_STATUS[0] == "idle"

    def test_contains_complete(self) -> None:
        assert PRINT_STATUS[9] == "complete"

    def test_contains_paused(self) -> None:
        assert PRINT_STATUS[6] == "paused"

    def test_contains_printing(self) -> None:
        assert PRINT_STATUS[3] == "printing"

    def test_contains_stopped(self) -> None:
        assert PRINT_STATUS[8] == "stopped"

    def test_all_values_are_strings(self) -> None:
        assert all(isinstance(v, str) for v in PRINT_STATUS.values())

    def test_all_keys_are_ints(self) -> None:
        assert all(isinstance(k, int) for k in PRINT_STATUS.keys())


# ---------------------------------------------------------------------------
# make_msg()
# ---------------------------------------------------------------------------

class TestMakeMsg:
    def test_returns_valid_json_string(self) -> None:
        raw = make_msg(CMD_STATUS, {})
        parsed = json.loads(raw)  # must not raise
        assert isinstance(parsed, dict)

    def test_cmd_field_matches_argument(self) -> None:
        parsed = json.loads(make_msg(CMD_START, {"Filename": "test.gcode"}))
        assert parsed["Data"]["Cmd"] == CMD_START

    def test_data_payload_is_embedded(self) -> None:
        payload = {"Filename": "my_model.gcode", "StartLayer": 0}
        parsed = json.loads(make_msg(CMD_START, payload))
        assert parsed["Data"]["Data"] == payload

    def test_topic_includes_mainboard_id(self) -> None:
        parsed = json.loads(make_msg(CMD_STATUS, {}, mainboard_id="abc123"))
        assert parsed["Topic"] == "sdcp/request/abc123"

    def test_request_id_is_32_chars_when_not_supplied(self) -> None:
        parsed = json.loads(make_msg(CMD_STATUS, {}))
        assert len(parsed["Data"]["RequestID"]) == 32

    def test_explicit_request_id_is_preserved(self) -> None:
        rid = "deadbeef" * 4  # 32 chars
        parsed = json.loads(make_msg(CMD_STATUS, {}, request_id=rid))
        assert parsed["Data"]["RequestID"] == rid

    def test_envelope_id_matches_request_id(self) -> None:
        parsed = json.loads(make_msg(CMD_ATTRS, {}))
        assert parsed["Id"] == parsed["Data"]["RequestID"]

    def test_from_field_is_present(self) -> None:
        parsed = json.loads(make_msg(CMD_STATUS, {}))
        assert "From" in parsed["Data"]

    def test_timestamp_is_positive_int(self) -> None:
        parsed = json.loads(make_msg(CMD_STATUS, {}))
        ts = parsed["Data"]["TimeStamp"]
        assert isinstance(ts, int) and ts > 0

    def test_empty_mainboard_id_is_valid(self) -> None:
        raw = make_msg(CMD_STATUS, {})
        parsed = json.loads(raw)
        assert parsed["Data"]["MainboardID"] == ""


# ---------------------------------------------------------------------------
# decode_printinfo()
# ---------------------------------------------------------------------------

class TestDecodePrintinfo:
    def test_passthrough_for_plain_keys(self) -> None:
        raw = {"Status": 3, "Filename": "test.gcode"}
        assert decode_printinfo(raw) == raw

    def test_decodes_hex_encoded_key(self) -> None:
        # "TotalExtrusion" encoded as space-separated hex bytes
        hex_key = "54 6F 74 61 6C 45 78 74 72 75 73 69 6F 6E 00"
        raw = {hex_key: 1234.5}
        result = decode_printinfo(raw)
        assert "TotalExtrusion" in result
        assert result["TotalExtrusion"] == 1234.5

    def test_normalises_filename_capitalisation(self) -> None:
        """FileName (capital N) must be aliased to Filename."""
        raw = {"FileName": "cube.gcode", "Status": 9}
        result = decode_printinfo(raw)
        assert "Filename" in result
        assert "FileName" not in result
        assert result["Filename"] == "cube.gcode"

    def test_existing_filename_not_overwritten(self) -> None:
        """If both spellings are somehow present, Filename takes precedence."""
        raw = {"Filename": "correct.gcode", "FileName": "wrong.gcode"}
        result = decode_printinfo(raw)
        assert result["Filename"] == "correct.gcode"
        # FileName must be dropped since Filename already existed
        assert "FileName" not in result

    def test_non_hex_multi_word_keys_are_preserved(self) -> None:
        """Keys that look like multiple words but aren't hex must pass through."""
        raw = {"Not Hex": 42}
        result = decode_printinfo(raw)
        assert "Not Hex" in result

    def test_empty_dict(self) -> None:
        assert decode_printinfo({}) == {}


# ---------------------------------------------------------------------------
# _deep_merge()
# ---------------------------------------------------------------------------

class TestDeepMerge:
    def test_flat_merge(self) -> None:
        base = {"a": 1}
        result = _deep_merge(base, {"b": 2})
        assert result == {"a": 1, "b": 2}

    def test_overwrites_scalar(self) -> None:
        base = {"a": 1}
        _deep_merge(base, {"a": 99})
        assert base["a"] == 99

    def test_nested_dict_merged_recursively(self) -> None:
        base = {"temps": {"nozzle": 200, "bed": 60}}
        _deep_merge(base, {"temps": {"nozzle": 210}})
        assert base["temps"]["nozzle"] == 210
        assert base["temps"]["bed"] == 60   # unrelated key preserved

    def test_nested_scalar_replaced_by_dict(self) -> None:
        base = {"x": 1}
        _deep_merge(base, {"x": {"nested": True}})
        assert base["x"] == {"nested": True}

    def test_returns_base_object(self) -> None:
        base = {"a": 1}
        result = _deep_merge(base, {"b": 2})
        assert result is base

    def test_empty_update_leaves_base_unchanged(self) -> None:
        base = {"key": "value"}
        _deep_merge(base, {})
        assert base == {"key": "value"}

    def test_max_keys_guard(self) -> None:
        """Merging beyond max_keys should not raise, just stop early."""
        base: dict = {}
        update = {str(i): i for i in range(200)}
        _deep_merge(base, update, max_keys=50)
        assert len(base) <= 51  # at most max_keys + 1 during the check


# ---------------------------------------------------------------------------
# filament_mm_to_grams()
# ---------------------------------------------------------------------------

class TestFilamentMmToGrams:
    def test_known_value_1000mm_pla(self) -> None:
        """1000 mm of 1.75 mm PLA (density 1.24 g/cm³) ≈ 3.8 g."""
        result = filament_mm_to_grams(1000.0)
        expected = round(math.pi * (0.0875 ** 2) * 100 * 1.24, 1)
        assert result == expected

    def test_zero_returns_zero(self) -> None:
        assert filament_mm_to_grams(0.0) == 0.0

    def test_higher_density_gives_more_grams(self) -> None:
        pla  = filament_mm_to_grams(1000.0, density=1.24)
        petg = filament_mm_to_grams(1000.0, density=1.27)
        assert petg > pla

    def test_custom_diameter(self) -> None:
        """3 mm filament should yield approximately 4× the mass of 1.75 mm."""
        g_175 = filament_mm_to_grams(1000.0, diameter=1.75)
        g_300 = filament_mm_to_grams(1000.0, diameter=3.00)
        ratio = g_300 / g_175
        # (3.0 / 1.75)² ≈ 2.94
        assert abs(ratio - (3.0 / 1.75) ** 2) < 0.1

    def test_result_is_rounded_to_one_decimal(self) -> None:
        result = filament_mm_to_grams(123.456)
        assert result == round(result, 1)
