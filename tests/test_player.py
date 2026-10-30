"""mpv IPC player behavior against a fake mpv server."""

from __future__ import annotations

import asyncio
import shutil
import tempfile
from pathlib import Path

import pytest

from radio_atlas.models import Station
from radio_atlas.player import (
    MpvIpc,
    MpvIpcError,
    MpvPlayer,
    NullPlayer,
    PlayerState,
    create_player,
)

from .fake_mpv import FakeMpv


@pytest.fixture
def short_dir():
    path = Path(tempfile.mkdtemp(prefix="ra-mpv-test-"))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
async def fake_mpv(short_dir):
    server = FakeMpv(short_dir / "mpv.sock")
    await server.start()
    try:
        yield server
    finally:
        await server.stop()


def station(uuid: str = "s1", name: str = "Jazz FM") -> Station:
    return Station(id=uuid, name=name, url="https://stream.example/live")


async def test_ipc_round_trip(fake_mpv):
    ipc = MpvIpc(fake_mpv.path)
    await ipc.connect()
    try:
        assert await ipc.command("get_property", "volume") == 70
        with pytest.raises(MpvIpcError, match="command failed"):
            await ipc.command("fail")
    finally:
        await ipc.close()


async def test_player_play_sends_loadfile_and_updates_state(fake_mpv):
    states: list[PlayerState] = []
    player = MpvPlayer(ipc=MpvIpc(fake_mpv.path), on_state=states.append)
    await player.start()
    assert player.available is True
    try:
        assert await player.play(station()) is True
        command = await fake_mpv.wait_for_command("loadfile")
        assert command["command"][1] == "https://stream.example/live"
        assert player.state.status == "playing"
        assert player.state.station is not None
        assert player.state.station.name == "Jazz FM"
        assert states
    finally:
        await player.close()


async def test_media_title_event_updates_track(fake_mpv):
    player = MpvPlayer(ipc=MpvIpc(fake_mpv.path))
    await player.start()
    try:
        await player.play(station())
        await fake_mpv.emit(
            {
                "event": "property-change",
                "id": 1,
                "name": "media-title",
                "data": "Miles Davis - So What",
            }
        )
        await asyncio.sleep(0.02)
        assert player.state.artist == "Miles Davis"
        assert player.state.title == "So What"
    finally:
        await player.close()


async def test_metadata_event_uses_icy_title(fake_mpv):
    player = MpvPlayer(ipc=MpvIpc(fake_mpv.path))
    await player.start()
    try:
        await player.play(station())
        await fake_mpv.emit(
            {
                "event": "property-change",
                "id": 2,
                "name": "metadata",
                "data": {"icy-title": "Something - Else"},
            }
        )
        await asyncio.sleep(0.02)
        assert player.state.artist == "Something"
        assert player.state.title == "Else"
    finally:
        await player.close()


async def test_pause_and_volume_commands(fake_mpv):
    player = MpvPlayer(ipc=MpvIpc(fake_mpv.path))
    await player.start()
    try:
        await player.play(station())
        assert await player.toggle_pause() is True
        assert player.state.status == "paused"
        assert await player.toggle_pause() is False
        assert player.state.status == "playing"

        assert await player.set_volume(55) == 55
        assert player.state.volume == 55
        assert await player.set_volume(500) == 100
        assert await player.toggle_mute() is True
        assert player.state.muted is True
    finally:
        await player.close()


async def test_end_file_error_marks_failure(fake_mpv):
    player = MpvPlayer(ipc=MpvIpc(fake_mpv.path))
    await player.start()
    try:
        await player.play(station())
        await fake_mpv.emit(
            {"event": "end-file", "reason": "error", "error": "loading failed"}
        )
        await asyncio.sleep(0.02)
        assert player.state.status == "error"
        assert player.state.error == "Stream failed to play"
    finally:
        await player.close()


async def test_stop_clears_station(fake_mpv):
    player = MpvPlayer(ipc=MpvIpc(fake_mpv.path))
    await player.start()
    try:
        await player.play(station())
        assert await player.stop() is True
        assert player.state.status == "stopped"
        assert player.state.station is None
    finally:
        await player.close()


async def test_socket_path_stays_under_macos_limit():
    player = MpvPlayer()
    path = player._socket_location()
    try:
        assert len(str(path)) < 104
        assert path.name == "mpv.sock"
    finally:
        shutil.rmtree(path.parent, ignore_errors=True)


async def test_missing_mpv_returns_null_player():
    player = create_player(mpv_path="/definitely/not/a/mpv")
    assert isinstance(player, NullPlayer)
    assert player.available is False
    assert await player.start() is False
    assert await player.play(station()) is False
    assert "mpv" in player.state.error


def test_state_parse_track():
    state = PlayerState(status="playing", volume=70)
    assert state.title == ""
