"""Siralama 1. kullaniciya Discord rolunu verir / digerlerinden alir."""
from __future__ import annotations

import discord

import economy
from settings import get_guild_id, get_top1_role_id
from storage import load_all, save_all

_client: discord.Client | None = None
_META_KEY = "__meta__"
_HOLDER_KEY = "top1_role_holder"


def bind_bot(client: discord.Client) -> None:
    global _client
    _client = client


def _last_holder() -> int | None:
    raw = load_all().get(_META_KEY, {}).get(_HOLDER_KEY)
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _set_holder(user_id: int | None) -> None:
    data = load_all()
    meta = data.setdefault(_META_KEY, {})
    if user_id is None:
        meta.pop(_HOLDER_KEY, None)
    else:
        meta[_HOLDER_KEY] = user_id
    if not meta:
        data.pop(_META_KEY, None)
    save_all(data)


async def _fetch_member(guild: discord.Guild, user_id: int) -> discord.Member | None:
    member = guild.get_member(user_id)
    if member is not None:
        return member
    try:
        return await guild.fetch_member(user_id)
    except discord.NotFound:
        return None


async def _remove_role(
    guild: discord.Guild, role: discord.Role, user_id: int
) -> None:
    member = await _fetch_member(guild, user_id)
    if member is None or role not in member.roles:
        return
    try:
        await member.remove_roles(role, reason="Siralama 1. degisti")
        print(f"Top1 rolu alindi: {user_id}", flush=True)
    except discord.Forbidden:
        print(f"Rol alinamadi: {user_id} (bot yetkisi / rol sirasi)", flush=True)


async def _add_role(guild: discord.Guild, role: discord.Role, user_id: int) -> bool:
    member = await _fetch_member(guild, user_id)
    if member is None:
        print(f"Top1 uyesi sunucuda bulunamadi: {user_id}", flush=True)
        return False
    if role in member.roles:
        return True
    try:
        await member.add_roles(role, reason="Siralama 1.")
        print(f"Top1 rolu verildi: {user_id}", flush=True)
        return True
    except discord.Forbidden:
        print(f"Rol verilemedi: {user_id} (bot yetkisi / rol sirasi)", flush=True)
        return False


async def _strip_stray_roles(
    guild: discord.Guild, role: discord.Role, leader_id: int
) -> None:
    """Rolu sadece gercek 1.'de birak; digerlerinden al."""
    for uid, _ in economy.top(50):
        if uid == leader_id:
            continue
        member = await _fetch_member(guild, uid)
        if member is not None and role in member.roles:
            await _remove_role(guild, role, uid)


async def sync_top1_role(guild: discord.Guild) -> None:
    role_id = get_top1_role_id()
    role = guild.get_role(role_id)
    if role is None:
        print(f"UYARI: Top1 rolu bulunamadi (id={role_id})", flush=True)
        return

    rows = economy.top(1)
    top_uid: int | None = rows[0][0] if rows else None
    prev_uid = _last_holder()

    if top_uid is None:
        if prev_uid is not None:
            await _remove_role(guild, role, prev_uid)
        for member in list(role.members):
            await _remove_role(guild, role, member.id)
        _set_holder(None)
        return

    if prev_uid is not None and prev_uid != top_uid:
        await _remove_role(guild, role, prev_uid)

    if prev_uid is None:
        await _strip_stray_roles(guild, role, top_uid)

    for member in list(role.members):
        if member.id != top_uid:
            await _remove_role(guild, role, member.id)

    member = await _fetch_member(guild, top_uid)
    if member is None:
        return

    if role not in member.roles:
        if not await _add_role(guild, role, top_uid):
            return

    _set_holder(top_uid)


async def sync_for_configured_guild() -> None:
    if _client is None:
        return
    gid = get_guild_id()
    if not gid.isdigit():
        return
    guild = _client.get_guild(int(gid))
    if guild is None:
        print(f"UYARI: Sunucu cache'de yok (id={gid}), top1 rol atlandi", flush=True)
        return
    await sync_top1_role(guild)


def schedule_sync() -> None:
    if _client is None:
        return
    try:
        _client.loop.create_task(sync_for_configured_guild())
    except RuntimeError:
        pass
