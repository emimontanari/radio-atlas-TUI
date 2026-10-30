"""A tiny in-process fake for mpv's newline-delimited JSON IPC."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any


class FakeMpv:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.commands: list[dict[str, Any]] = []
        self._server: asyncio.AbstractServer | None = None
        self._clients: set[asyncio.StreamWriter] = set()
        self._closed = False

    async def start(self) -> None:
        self._server = await asyncio.start_unix_server(
            self._handle, path=str(self.path)
        )

    async def _handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        self._clients.add(writer)
        try:
            while line := await reader.readline():
                payload = json.loads(line.decode("utf-8"))
                self.commands.append(payload)
                command = payload.get("command") or []
                name = command[0] if command else ""
                response: dict[str, Any] = {
                    "request_id": payload.get("request_id"),
                    "error": "success",
                }
                if name == "get_property":
                    response["data"] = 70
                elif name == "fail":
                    response["error"] = "command failed"
                try:
                    writer.write(
                        (json.dumps(response) + "\n").encode("utf-8")
                    )
                    await writer.drain()
                except (ConnectionError, asyncio.CancelledError):
                    break
                if name == "quit":
                    break
        finally:
            self._clients.discard(writer)
            writer.close()

    def names(self) -> list[str]:
        return [command["command"][0] for command in self.commands if command.get("command")]

    async def wait_for_command(self, name: str, timeout: float = 1.0) -> dict[str, Any]:
        async def poll() -> dict[str, Any]:
            while True:
                for command in self.commands:
                    if command.get("command") and command["command"][0] == name:
                        return command
                await asyncio.sleep(0.005)

        return await asyncio.wait_for(poll(), timeout)

    async def emit(self, event: dict[str, Any]) -> None:
        data = (json.dumps(event) + "\n").encode("utf-8")
        for writer in list(self._clients):
            try:
                writer.write(data)
                await writer.drain()
            except (ConnectionError, asyncio.CancelledError):
                self._clients.discard(writer)

    async def stop(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
        for writer in list(self._clients):
            writer.close()
        self._clients.clear()
        self.path.unlink(missing_ok=True)
