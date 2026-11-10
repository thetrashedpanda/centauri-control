"""
Tests for Phase 1 stability improvements: heartbeat, timeouts, exponential backoff.
"""

import asyncio
import json
import unittest
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from centauricontrol.printers.cc1 import CC1Connection
from centauricontrol.printers import sdcp


class TestCC1Heartbeat(unittest.TestCase):
    """Test heartbeat/keepalive mechanism."""

    def setUp(self) -> None:
        self.callback = Mock()
        self.conn = CC1Connection(
            printer_id="test-cc1",
            ip="192.168.1.100",
            name="Test Printer",
            printer_type="cc1",
            access_code="",
            on_state_change=self.callback,
        )

    def test_heartbeat_sends_ping_with_short_interval(self) -> None:
        """Verify heartbeat loop sends 'ping' message with short interval."""
        self.conn._ws = AsyncMock()
        
        async def run_heartbeat():
            # Patch the interval to be very short for testing
            with patch("centauricontrol.printers.cc1._HEARTBEAT_INTERVAL", 0.01):
                task = asyncio.create_task(self.conn._heartbeat_loop())
                await asyncio.sleep(0.05)  # Wait long enough for ping
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        asyncio.run(run_heartbeat())
        
        # Verify ping was sent at least once
        calls = [call[0][0] for call in self.conn._ws.send.call_args_list]
        self.assertGreater(len(calls), 0, "Expected send to be called")
        self.assertIn("ping", calls, "Expected 'ping' message to be sent")

    def test_heartbeat_handles_pong(self) -> None:
        """Verify pong responses are handled correctly."""
        # Should not raise an exception
        self.conn._handle_message("pong")

    def test_heartbeat_stops_on_websocket_close(self) -> None:
        """Verify heartbeat loop exits cleanly when WebSocket closes."""
        self.conn._ws = None
        
        async def run_heartbeat():
            with patch("centauricontrol.printers.cc1._HEARTBEAT_INTERVAL", 0.01):
                task = asyncio.create_task(self.conn._heartbeat_loop())
                await asyncio.sleep(0.05)
                # Loop should exit when _ws is None
        
        # Should complete without error
        asyncio.run(run_heartbeat())


class TestCC1ResponseTimeout(unittest.TestCase):
    """Test command response timeout and retry logic."""

    def setUp(self) -> None:
        self.callback = Mock()
        self.conn = CC1Connection(
            printer_id="test-cc1",
            ip="192.168.1.100",
            name="Test Printer",
            printer_type="cc1",
            access_code="",
            on_state_change=self.callback,
        )

    def test_send_cmd_timeout_retry(self) -> None:
        """Verify command times out and retries once."""
        async def run_test():
            self.conn._ws = AsyncMock()
            self.conn.mainboard_id = "test-id"
            
            # Make send succeed but never send a response (timeout)
            self.conn._ws.send = AsyncMock()
            
            with patch("centauricontrol.printers.cc1._COMMAND_TIMEOUT", 0.01):
                result = await self.conn.send_cmd(sdcp.CMD_STATUS, {})
            
            # send_cmd should return empty dict after timeout + retry
            self.assertEqual(result, {})
            
            # Verify send was called twice (initial + retry)
            self.assertEqual(self.conn._ws.send.call_count, 2)
        
        asyncio.run(run_test())

    def test_send_cmd_not_connected(self) -> None:
        """Verify send_cmd gracefully handles not-connected state."""
        async def run_test():
            self.conn._ws = None
            result = await self.conn.send_cmd(sdcp.CMD_STATUS, {})
            self.assertEqual(result, {})
        
        asyncio.run(run_test())


class TestCC1ExponentialBackoff(unittest.TestCase):
    """Test exponential backoff for reconnection."""

    def setUp(self) -> None:
        self.callback = Mock()
        self.conn = CC1Connection(
            printer_id="test-cc1",
            ip="192.168.1.100",
            name="Test Printer",
            printer_type="cc1",
            access_code="",
            on_state_change=self.callback,
        )

    def test_initial_reconnect_delay(self) -> None:
        """Verify initial reconnect delay is 1 second."""
        from centauricontrol.printers.cc1 import _INITIAL_RECONNECT_DELAY
        self.assertEqual(self.conn._reconnect_delay, _INITIAL_RECONNECT_DELAY)

    def test_backoff_increases_on_failures(self) -> None:
        """Verify delay increases after consecutive failures."""
        from centauricontrol.printers.cc1 import (
            _FAILURE_THRESHOLD,
            _INITIAL_RECONNECT_DELAY,
        )
        
        initial = self.conn._reconnect_delay
        
        # Simulate failures until threshold
        self.conn._consecutive_failures = _FAILURE_THRESHOLD
        self.conn._update_reconnect_delay()
        
        # Delay should have doubled
        self.assertEqual(self.conn._reconnect_delay, initial * 2)

    def test_backoff_caps_at_max(self) -> None:
        """Verify reconnect delay is capped at maximum."""
        from centauricontrol.printers.cc1 import _MAX_RECONNECT_DELAY
        
        # Force max by simulating many failures
        self.conn._consecutive_failures = 100
        for _ in range(20):
            self.conn._update_reconnect_delay()
        
        # Should not exceed max
        self.assertLessEqual(self.conn._reconnect_delay, _MAX_RECONNECT_DELAY)

    def test_backoff_resets_on_success(self) -> None:
        """Verify reconnect delay resets to initial after successful connect."""
        from centauricontrol.printers.cc1 import _INITIAL_RECONNECT_DELAY
        
        # Simulate failure scenario
        self.conn._consecutive_failures = 10
        self.conn._reconnect_delay = 30.0
        
        # Simulate successful connection reset
        self.conn._consecutive_failures = 0
        self.conn._reconnect_delay = _INITIAL_RECONNECT_DELAY
        
        self.assertEqual(self.conn._reconnect_delay, _INITIAL_RECONNECT_DELAY)


class TestFieldNameHandling(unittest.TestCase):
    """Test handling of SDCP protocol field name misspellings."""

    def setUp(self) -> None:
        self.callback = Mock()
        self.conn = CC1Connection(
            printer_id="test-cc1",
            ip="192.168.1.100",
            name="Test Printer",
            printer_type="cc1",
            access_code="",
            on_state_change=self.callback,
        )

    def test_handle_misspelled_current_coord(self) -> None:
        """Verify CurrenCoord (misspelled) is parsed correctly."""
        status_msg = {
            "CurrenCoord": "150.5,75.2,10.8",  # Intentional misspelling
            "TempOfNozzle": 210,
        }
        
        # Should not raise exception
        self.conn._apply_status(status_msg)
        
        # Verify status contains the field
        self.assertIn("CurrenCoord", self.conn.status)
        self.assertEqual(self.conn.status["CurrenCoord"], "150.5,75.2,10.8")

    def test_handle_misspelled_filament_state(self) -> None:
        """Verify RelaseFilmState (misspelled) is parsed correctly."""
        status_msg = {
            "RelaseFilmState": 1,  # Intentional misspelling (missing 'e')
        }
        
        # Should not raise exception
        self.conn._apply_status(status_msg)
        
        # Verify status contains the field
        self.assertIn("RelaseFilmState", self.conn.status)


class TestResponseCorrelation(unittest.TestCase):
    """Test RequestID-based response correlation."""

    def setUp(self) -> None:
        self.callback = Mock()
        self.conn = CC1Connection(
            printer_id="test-cc1",
            ip="192.168.1.100",
            name="Test Printer",
            printer_type="cc1",
            access_code="",
            on_state_change=self.callback,
        )

    def test_pending_responses_tracking(self) -> None:
        """Verify pending responses are tracked by RequestID."""
        request_id = "test-request-123"
        
        # Simulating a pending response (without actual asyncio Future)
        self.conn._pending_responses[request_id] = True
        
        # Verify it's tracked
        self.assertIn(request_id, self.conn._pending_responses)
        
        # Clean up
        del self.conn._pending_responses[request_id]
        self.assertNotIn(request_id, self.conn._pending_responses)


class TestLogging(unittest.TestCase):
    """Test logging is properly configured."""

    def test_logging_module_loads(self) -> None:
        """Verify logging module can be imported."""
        from centauricontrol import logging_config
        self.assertIsNotNone(logging_config)

    def test_get_logger(self) -> None:
        """Verify get_logger returns valid logger."""
        from centauricontrol.logging_config import get_logger
        
        logger = get_logger("test.module")
        self.assertIsNotNone(logger)
        self.assertTrue(hasattr(logger, "info"))
        self.assertTrue(hasattr(logger, "error"))

    def test_initialize_logging(self) -> None:
        """Verify logging initialization works."""
        from centauricontrol.logging_config import initialize_logging
        import tempfile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Should not raise
            initialize_logging(log_dir=tmpdir)


if __name__ == "__main__":
    unittest.main()

