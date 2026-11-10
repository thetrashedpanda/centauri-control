from __future__ import annotations

from types import SimpleNamespace

from centauricontrol.api import http


class _StreamResponse:
    def __init__(self, chunks: list[bytes | Exception]) -> None:
        self.headers = {"Content-Type": "multipart/x-mixed-replace; boundary=frame"}
        self._chunks = iter(chunks)

    def __enter__(self) -> _StreamResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, _size: int) -> bytes:
        chunk = next(self._chunks)
        if isinstance(chunk, Exception):
            raise chunk
        return chunk


class _ClientWriter:
    def __init__(self) -> None:
        self.chunks: list[bytes] = []

    def write(self, chunk: bytes) -> None:
        if self.chunks:
            raise BrokenPipeError("client disconnected")
        self.chunks.append(chunk)

    def flush(self) -> None:
        return None


def test_camera_proxy_reconnects_after_upstream_drop(monkeypatch, tmp_path) -> None:
    opened: list[float] = []
    responses = iter(
        [
            _StreamResponse([b"first-frame", ConnectionResetError("upstream dropped")]),
            _StreamResponse([b"next-frame"]),
        ]
    )

    def open_upstream(_request, timeout: float):
        opened.append(timeout)
        return next(responses)

    monkeypatch.setattr(http.urllib.request, "urlopen", open_upstream)
    monkeypatch.setattr(http.time, "sleep", lambda _delay: None)

    registry = SimpleNamespace(
        get=lambda _printer_id: SimpleNamespace(camera_url="http://printer.local/video")
    )
    handler_class = http.make_handler_class(None, None, registry, None)
    handler = object.__new__(handler_class)
    handler.path = "/camera/printer-1/stream"
    handler.wfile = _ClientWriter()
    handler._check_auth = lambda _path: True
    response_codes: list[int] = []
    headers: list[tuple[str, str]] = []
    handler.send_response = response_codes.append
    handler.send_header = lambda name, value: headers.append((name, value))
    handler.end_headers = lambda: None
    handler._json = lambda *_args: (_ for _ in ()).throw(AssertionError("unexpected error response"))

    handler._camera_proxy(handler.path)

    assert opened == [http._CAMERA_READ_TIMEOUT_SECONDS] * 2
    assert response_codes == [200]
    assert handler.wfile.chunks == [b"first-frame"]
    assert ("X-Accel-Buffering", "no") in headers
