"""mpv playback over its newline-delimited JSON IPC socket."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable

from .config import mpv_override
from .models import Station, parse_track

MEDIA_TITLE_ID = 1
METADATA_ID = 2
CONNECT_TIMEOUT = 8.0  # first launch after install can be slow on macOS
COMMAND_TIMEOUT = 2.0


class MpvIpcError(RuntimeError):
    """Raised when mpv answers a command with an error."""


class PlayerUnavailable(RuntimeError):
    """Raised when mpv is missing or cannot start."""


@dataclass(slots=True)
class PlayerState:
    status: str = "stopped"
    station: Station | None = None
    title: str = ""
    artist: str = ""
    volume: int = 70
    muted: bool = False
    error: str = ""

    @property
    def playing(self) -> bool:
        return self.status == "playing"

    @property
    def paused(self) -> bool:
        return self.status == "paused"

    @property
    def has_track(self) -> bool:
        return bool(self.title or self.artist)


class MpvIpc:
    """One JSON IPC connection to an mpv instance."""

    def __init__(
        self,
        path: Path | str,
        *,
        on_event: Callable[[dict[str, Any]], None] | None = None,
        timeout: float = COMMAND_TIMEOUT,
    ) -> None:
        self.path = Path(path)
        self.on_event = on_event
        self.timeout = timeout
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._next_id = 1
        self._closed = False

    async def connect(self) -> None:
        self._reader, self._writer = await asyncio.open_unix_connection(
            str(self.path)
        )
        self._reader_task = asyncio.create_task(self._read_loop())

    async def command(self, name: str, *args: Any, timeout: float | None = None) -> Any:
        if self._writer is None or self._closed:
            raise MpvIpcError("mpv IPC is not connected")
        request_id = self._next_id
        self._next_id += 1
        payload = {"command": [name, *args], "request_id": request_id}
        future: asyncio.Future[dict[str, Any]] = (
            asyncio.get_running_loop().create_future()
        )
        self._pending[request_id] = future
        try:
            self._writer.write((json.dumps(payload) + "\n").encode("utf-8"))
            await self._writer.drain()
            response = await asyncio.wait_for(
                future, timeout if timeout is not None else self.timeout
            )
        except asyncio.TimeoutError as error:
            raise MpvIpcError(f"mpv did not answer {name}") from error
        finally:
            self._pending.pop(request_id, None)
        error = response.get("error", "success")
        if error != "success":
            raise MpvIpcError(str(error))
        return response.get("data")

    async def _read_loop(self) -> None:
        assert self._reader is not None
        try:
            while line := await self._reader.readline():
                try:
                    message = json.loads(line.decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    continue
                if not isinstance(message, dict):
                    continue
                request_id = message.get("request_id")
                if isinstance(request_id, int):
                    future = self._pending.get(request_id)
                    if future is not None and not future.done():
                        future.set_result(message)
                event = message.get("event")
                if isinstance(event, str) and self.on_event is not None:
                    try:
                        self.on_event(message)
                    except Exception:
                        pass
        except (ConnectionError, asyncio.CancelledError, OSError):
            pass
        finally:
            for future in self._pending.values():
                if not future.done():
                    future.set_exception(MpvIpcError("mpv IPC disconnected"))
            self._pending.clear()

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._reader_task is not None:
            self._reader_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._reader_task
            self._reader_task = None
        if self._writer is not None:
            self._writer.close()
            with contextlib.suppress(Exception):
                await self._writer.wait_closed()
            self._writer = None


class MpvPlayer:
    def __init__(
        self,
        *,
        mpv_path: str | None = None,
        ipc: MpvIpc | None = None,
        on_state: Callable[[PlayerState], None] | None = None,
        socket_dir: Path | None = None,
        volume: int = 70,
        muted: bool = False,
    ) -> None:
        self._binary = mpv_path or mpv_override() or shutil.which("mpv")
        self._ipc = ipc
        self._injected_ipc = ipc is not None
        self._on_state = on_state
        self._socket_dir = Path(socket_dir) if socket_dir is not None else None
        self._process: asyncio.subprocess.Process | None = None
        self._started = False
        self.state = PlayerState(volume=max(0, min(100, volume)), muted=muted)

    @property
    def available(self) -> bool:
        if self._injected_ipc:
            return True
        return bool(self._binary and Path(self._binary).exists())

    @property
    def status(self) -> str:
        return self.state.status

    def _notify(self) -> None:
        if self._on_state is not None:
            try:
                self._on_state(replace(self.state))
            except Exception:
                pass

    def _set(self, **changes: Any) -> None:
        self.state = replace(self.state, **changes)
        self._notify()

    def _socket_location(self) -> Path:
        if self._socket_dir is not None:
            self._socket_dir.mkdir(parents=True, exist_ok=True)
            return self._socket_dir / "mpv.sock"
        candidates = [tempfile.gettempdir(), "/tmp"]
        for base in candidates:
            directory = Path(tempfile.mkdtemp(prefix="ra-mpv-", dir=base))
            path = directory / "mpv.sock"
            if len(str(path)) < 100:
                self._socket_dir = directory
                return path
            shutil.rmtree(directory, ignore_errors=True)
        raise PlayerUnavailable("cannot create a short enough mpv socket path")

    async def start(self) -> bool:
        if self._started:
            return True
        if self._injected_ipc:
            assert self._ipc is not None
            self._ipc.on_event = self._handle_event
            await self._ipc.connect()
            self._started = True
            await self._observe()
            return True
        if not self.available:
            self._set(
                status="unavailable",
                error="mpv is not installed. Install it to play radio.",
            )
            return False
        try:
            socket_path = self._socket_location()
        except PlayerUnavailable as error:
            self._set(status="error", error=str(error))
            return False
        assert self._binary is not None
        args = [
            self._binary,
            "--no-video",
            "--idle=yes",
            "--no-terminal",
            "--really-quiet",
            f"--input-ipc-server={socket_path}",
            f"--volume={self.state.volume}",
            "--cache=yes",
            "--cache-secs=10",
        ]
        try:
            self._process = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except OSError as error:
            self._set(status="error", error=f"cannot start mpv: {error}")
            return False

        ipc = MpvIpc(socket_path, on_event=self._handle_event)
        deadline = asyncio.get_running_loop().time() + CONNECT_TIMEOUT
        while True:
            try:
                await ipc.connect()
                break
            except (ConnectionError, OSError):
                if self._process.returncode is not None:
                    self._set(
                        status="error",
                        error="mpv exited before the player could connect",
                    )
                    return False
                if asyncio.get_running_loop().time() >= deadline:
                    self._set(status="error", error="mpv did not open its IPC socket")
                    await self._terminate()
                    return False
                await asyncio.sleep(0.05)
        self._ipc = ipc
        self._started = True
        await self._observe()
        return True

    async def _observe(self) -> None:
        if self._ipc is None:
            return
        for request_id, name in ((MEDIA_TITLE_ID, "media-title"), (METADATA_ID, "metadata")):
            with contextlib.suppress(MpvIpcError):
                await self._ipc.command("observe_property", request_id, name)

    async def play(self, station: Station) -> bool:
        if not self._started and not await self.start():
            return False
        assert self._ipc is not None
        self._set(
            status="playing",
            station=station,
            title="",
            artist="",
            error="",
        )
        try:
            await self._ipc.command("loadfile", station.url, "replace")
        except MpvIpcError as error:
            self._set(status="error", error=str(error))
            return False
        return True

    async def toggle_pause(self) -> bool:
        if not self._started or self.state.station is None:
            return False
        assert self._ipc is not None
        paused = not self.state.paused
        try:
            await self._ipc.command("set_property", "pause", paused)
        except MpvIpcError as error:
            self._set(error=str(error))
            return self.state.paused
        self._set(status="paused" if paused else "playing", error="")
        return paused

    async def stop(self) -> bool:
        if not self._started:
            return False
        assert self._ipc is not None
        with contextlib.suppress(MpvIpcError, OSError):
            await self._ipc.command("stop")
        self._set(
            status="stopped",
            station=None,
            title="",
            artist="",
            error="",
        )
        return True

    async def set_volume(self, value: int) -> int:
        volume = max(0, min(100, int(value)))
        self._set(volume=volume)
        if self._started and self._ipc is not None:
            with contextlib.suppress(MpvIpcError, OSError):
                await self._ipc.command("set_property", "volume", volume)
        return volume

    async def toggle_mute(self) -> bool:
        muted = not self.state.muted
        self._set(muted=muted)
        if self._started and self._ipc is not None:
            with contextlib.suppress(MpvIpcError, OSError):
                await self._ipc.command("set_property", "mute", muted)
        return muted

    def _handle_event(self, event: dict[str, Any]) -> None:
        name = event.get("event")
        if name == "property-change":
            self._handle_property(event)
        elif name == "file-loaded":
            if self.state.station is not None and self.state.status != "paused":
                self._set(status="playing", error="")
        elif name == "end-file":
            reason = event.get("reason")
            if reason == "error":
                self._set(status="error", error="Stream failed to play")
            elif self.state.status != "error":
                self._set(status="stopped", error="")
        elif name == "idle":
            if self.state.status != "error":
                self._set(status="stopped")

    def _handle_property(self, event: dict[str, Any]) -> None:
        property_id = event.get("id")
        data = event.get("data")
        if property_id == MEDIA_TITLE_ID and isinstance(data, str):
            artist, title = parse_track(data, self.state.station.name if self.state.station else "")
            if title or artist:
                self._set(artist=artist, title=title)
        elif property_id == METADATA_ID and isinstance(data, dict):
            raw = data.get("icy-title") or data.get("StreamTitle") or ""
            if isinstance(raw, str) and raw:
                artist, title = parse_track(
                    raw, self.state.station.name if self.state.station else ""
                )
                self._set(artist=artist, title=title)

    async def _terminate(self) -> None:
        if self._process is None:
            return
        if self._process.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                with contextlib.suppress(ProcessLookupError):
                    self._process.kill()
                with contextlib.suppress(Exception):
                    await self._process.wait()
        self._process = None

    async def close(self) -> None:
        if self._ipc is not None:
            with contextlib.suppress(MpvIpcError, OSError, asyncio.TimeoutError):
                await self._ipc.command("quit", timeout=0.3)
            await self._ipc.close()
            self._ipc = None
        await self._terminate()
        if self._socket_dir is not None and self._process is None:
            shutil.rmtree(self._socket_dir, ignore_errors=True)
            self._socket_dir = None
        self._started = False


class NullPlayer:
    """Playback stand-in used when mpv is not installed."""

    available = False

    def __init__(self) -> None:
        self.state = PlayerState(
            status="unavailable",
            error="mpv is not installed. Install it to play radio.",
        )

    @property
    def status(self) -> str:
        return self.state.status

    async def start(self) -> bool:
        return False

    async def play(self, station: Station) -> bool:
        self.state = replace(
            self.state,
            station=station,
            status="unavailable",
            error="mpv is not installed. Install it to play radio.",
        )
        return False

    async def toggle_pause(self) -> bool:
        return False

    async def stop(self) -> bool:
        return False

    async def set_volume(self, value: int) -> int:
        self.state = replace(self.state, volume=max(0, min(100, int(value))))
        return self.state.volume

    async def toggle_mute(self) -> bool:
        self.state = replace(self.state, muted=not self.state.muted)
        return self.state.muted

    async def close(self) -> None:
        return None


def create_player(
    *,
    mpv_path: str | None = None,
    on_state: Callable[[PlayerState], None] | None = None,
    volume: int = 70,
    muted: bool = False,
) -> MpvPlayer | NullPlayer:
    """Return an mpv player when the binary exists, otherwise a no-op player."""
    resolved = mpv_path or mpv_override() or shutil.which("mpv")
    if resolved and Path(resolved).exists():
        return MpvPlayer(
            mpv_path=resolved, on_state=on_state, volume=volume, muted=muted
        )
    return NullPlayer()
