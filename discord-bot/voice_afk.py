"""Belirlenen ses kanalina baglanir ve AFK kalir."""
from __future__ import annotations

import asyncio

import discord

from settings import get_afk_voice_channel_id, get_guild_id

_client: discord.Client | None = None
_connecting = False


def bind_bot(client: discord.Client) -> None:
    global _client
    _client = client


def _voice_deps_ok() -> bool:
    try:
        import nacl  # noqa: F401
        import davey  # noqa: F401
    except ImportError:
        print(
            "SES ICIN EK PAKET GEREKLI:\n"
            "  pip install -r requirements.txt\n"
            "  (PyNaCl + davey)",
            flush=True,
        )
        return False
    return True


async def _resolve_channel(channel_id: int) -> discord.VoiceChannel | None:
    if _client is None:
        return None

    channel = _client.get_channel(channel_id)
    if isinstance(channel, discord.VoiceChannel):
        return channel

    gid = get_guild_id()
    if gid.isdigit():
        guild = _client.get_guild(int(gid))
        if guild is not None:
            ch = guild.get_channel(channel_id)
            if isinstance(ch, discord.VoiceChannel):
                return ch

    try:
        fetched = await _client.fetch_channel(channel_id)
    except discord.HTTPException:
        print(f"UYARI: Ses kanali bulunamadi ({channel_id})", flush=True)
        return None

    if isinstance(fetched, discord.VoiceChannel):
        return fetched
    print(f"UYARI: {channel_id} bir ses kanali degil", flush=True)
    return None


async def connect_afk_voice() -> None:
    global _connecting
    if _client is None or _connecting:
        return

    channel_id = get_afk_voice_channel_id()
    if channel_id is None:
        return
    if not _voice_deps_ok():
        return

    for vc in _client.voice_clients:
        if vc.channel and vc.channel.id == channel_id and vc.is_connected():
            return

    _connecting = True
    try:
        channel = await _resolve_channel(channel_id)
        if channel is None:
            return

        for vc in list(_client.voice_clients):
            if vc.channel != channel:
                await vc.disconnect(force=True)

        if _client.voice_clients:
            await _client.voice_clients[0].move_to(channel)
        else:
            await channel.connect(reconnect=True, self_deaf=True, self_mute=True)

        print(f"Ses kanalina baglandi: {channel.name} ({channel_id})", flush=True)
    except discord.Forbidden:
        print("Ses kanalina baglanamadi: yetki yok", flush=True)
    except discord.ClientException as e:
        print(f"Ses baglanti hatasi: {e}", flush=True)
    except Exception as e:
        print(f"Ses baglanti hatasi: {e}", flush=True)
    finally:
        _connecting = False


def schedule_reconnect(delay: float = 5.0) -> None:
    if _client is None:
        return

    async def _reconnect() -> None:
        await asyncio.sleep(delay)
        await connect_afk_voice()

    try:
        _client.loop.create_task(_reconnect())
    except RuntimeError:
        pass
