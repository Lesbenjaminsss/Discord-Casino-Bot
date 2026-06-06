"""
Discord ekonomi + blackjack botu.
Tum komutlar SLASH (/para, /bj, ...) — Message Content Intent gerekmez.
"""
import asyncio
import sys
from datetime import timedelta

import discord
from discord import app_commands

import economy
from blackjack import BlackjackGame, hand_value, is_blackjack
from horse_racing import init_positions, payout as race_payout, race_embed, tick, winner
from stable import (
    BREEDS,
    STABLE_COST,
    buy_horse,
    collect_income,
    get_owned_horse,
    is_open,
    market_text,
    open_stable,
    owned_to_racer,
    random_npc_racers,
    record_race,
    stable_embed_text,
    total_income_per_hour,
)
from table_image import discord_file as bj_table_file
from top1_role import bind_bot, schedule_sync, sync_for_configured_guild, sync_top1_role
from voice_afk import bind_bot as bind_voice, connect_afk_voice, schedule_reconnect
from settings import (
    DAILY_SALARY,
    OWNER_ID,
    SALARY_COOLDOWN_SEC,
    START_BALANCE,
    TOP_COUNT,
    check_token,
    get_guild_id,
    get_token,
)

MEDALS = ("🥇", "🥈", "🥉")
_active_bj: dict[int, BlackjackGame] = {}
_active_race: set[int] = set()


def fmt_time(sec: int) -> str:
    return str(timedelta(seconds=max(0, sec)))


def is_owner(uid: int) -> bool:
    return uid == OWNER_ID


class EcoBot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)
        self._slash_synced = False

    async def on_ready(self) -> None:
        if not self._slash_synced:
            self._slash_synced = True
            await sync_slash_commands(self)

        print("=" * 50, flush=True)
        print("BOT AKTIF", flush=True)
        print(f"  {self.user} ({self.user.id})", flush=True)
        gid = get_guild_id()
        if gid.isdigit():
            print(f"  Sunucu ID: {gid} (komutlar bu sunucuda)", flush=True)
        else:
            print("  UYARI: DISCORD_GUILD_ID yok -> / komutlar gecikebilir", flush=True)
        print("  Discord'da / yaz -> komutlar gelmeli", flush=True)
        print("  Sahip komutlari: /paraver /yenile", flush=True)
        print("=" * 50, flush=True)
        await self.change_presence(activity=discord.Game(name="/yardim"))
        await sync_for_configured_guild()
        await connect_afk_voice()

    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        if self.user is None or member.id != self.user.id:
            return
        if before.channel is not None and after.channel is None:
            schedule_reconnect()


async def sync_slash_commands(bot: EcoBot) -> list[str]:
    """Slash komutlari Discord'a yukler."""
    gid = get_guild_id()
    try:
        if gid.isdigit():
            guild = discord.Object(id=int(gid))
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)
            where = f"sunucu {gid}"
        else:
            synced = await bot.tree.sync()
            where = "global (1 saate kadar surebilir)"
        names = [c.name for c in synced]
        print(f"Komutlar yuklendi [{where}]: {len(names)} adet", flush=True)
        for n in names:
            print(f"  /{n}", flush=True)
        return names
    except Exception as e:
        print(f"HATA komut yukleme: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return []


client = EcoBot()
bind_bot(client)
bind_voice(client)


async def user_name(uid: int, guild: discord.Guild | None) -> str:
    if guild:
        m = guild.get_member(uid)
        if m:
            return m.display_name
    try:
        u = await client.fetch_user(uid)
        return u.display_name
    except discord.NotFound:
        return f"Kullanici-{uid % 10000}"


async def leaderboard_embed(viewer: int, guild: discord.Guild | None) -> discord.Embed:
    rows = economy.top(TOP_COUNT)
    emb = discord.Embed(title=f"En Zengin {TOP_COUNT}", color=0xF1C40F)
    if not rows:
        emb.description = "Henuz kimse yok. /para ile basla."
        return emb

    names = await asyncio.gather(
        *[user_name(uid, guild) for uid, _ in rows],
        return_exceptions=True,
    )
    lines = []
    for i, ((uid, bal), nm) in enumerate(zip(rows, names, strict=True), 1):
        tag = MEDALS[i - 1] if i <= 3 else f"**{i}.**"
        name = nm if isinstance(nm, str) else "Oyuncu"
        mark = " <- sen" if uid == viewer else ""
        lines.append(f"{tag} **{name}** — **{bal:,}**{mark}")
    emb.description = "\n".join(lines)

    r = economy.rank_of(viewer)
    if r:
        pos, bal = r
        if pos > TOP_COUNT:
            emb.set_footer(text=f"Senin siran: #{pos} ({bal:,})")
        else:
            emb.set_footer(text=f"Sen #{pos}. siradasin")
    return emb


class BJView(discord.ui.View):
    def __init__(self, game: BlackjackGame):
        super().__init__(timeout=120)
        self.game = game

    async def interaction_check(self, i: discord.Interaction) -> bool:
        if i.user.id != self.game.user_id:
            await i.response.send_message("Bu el senin degil.", ephemeral=True)
            return False
        return True

    def _totals(self, reveal: bool) -> tuple[int | str, int | str]:
        g = self.game
        pv = hand_value(g.player)
        if reveal or g.finished or g.player_busted:
            return pv, hand_value(g.dealer)
        return pv, "?"

    def _desc(self, reveal: bool, bal: int | None = None) -> str:
        g = self.game
        pv, dv = self._totals(reveal)
        balance = bal if bal is not None else economy.balance(g.user_id)
        return (
            f"💰 **Bahis:** {g.bet:,} | **Bakiye:** {balance:,}\n"
            f"🎩 **Kurpiyer:** {dv}\n"
            f"🃏 **Senin elin:** {pv}"
        )

    def embed(self, reveal: bool = False) -> discord.Embed:
        g = self.game
        title = "🃏 Blackjack Masası"
        if g.finished:
            title = f"🃏 {g.outcome()[0]}"
        e = discord.Embed(title=title, color=0x1B4D3E)
        e.description = self._desc(reveal)
        e.set_image(url="attachment://blackjack.png")
        if not g.finished:
            e.set_footer(text="Kart çek veya dur")
        return e

    def _table(self, reveal: bool = False) -> discord.File:
        g = self.game
        hide = not reveal and not g.finished and not g.player_busted
        return bj_table_file(
            g.player,
            g.dealer,
            hide_dealer_first=hide,
        )

    async def finish(self, i: discord.Interaction) -> None:
        g = self.game
        pay = g.resolve_payout()
        if pay > 0:
            economy.add_money(g.user_id, pay)
        net = pay - g.bet
        bal = economy.balance(g.user_id)
        e = self.embed(reveal=True)
        base = self._desc(True, bal)
        if net > 0:
            e.color = 0x57F287
            e.description = f"{base}\n\n✅ **+{net:,}** kazandin!"
        elif net == 0:
            e.color = 0xFEE75C
            e.description = f"{base}\n\n↩️ Bahis iade edildi."
        else:
            e.color = 0xED4245
            e.description = f"{base}\n\n❌ **-{g.bet:,}** kaybettin."
        for c in self.children:
            c.disabled = True
        _active_bj.pop(g.user_id, None)
        await i.response.edit_message(
            embed=e, view=self, attachments=[self._table(reveal=True)]
        )
        schedule_sync()
        self.stop()

    @discord.ui.button(label="Kart cek", style=discord.ButtonStyle.primary)
    async def hit(self, i: discord.Interaction, _b: discord.ui.Button):
        if self.game.finished:
            return await i.response.defer()
        self.game.hit()
        if self.game.finished:
            return await self.finish(i)
        await i.response.edit_message(
            embed=self.embed(), view=self, attachments=[self._table()]
        )

    @discord.ui.button(label="Dur", style=discord.ButtonStyle.secondary)
    async def stand(self, i: discord.Interaction, _b: discord.ui.Button):
        if self.game.finished:
            return await i.response.defer()
        self.game.stand()
        await self.finish(i)

    async def on_timeout(self) -> None:
        g = self.game
        if g.user_id not in _active_bj:
            return
        g.stand()
        pay = g.resolve_payout()
        if pay > 0:
            economy.add_money(g.user_id, pay)
        _active_bj.pop(g.user_id, None)
        schedule_sync()


async def play_bj(user_id: int, bet: int, reply) -> None:
    if user_id in _active_bj:
        return await reply(content="Zaten bir elin var.", ephemeral=True)
    if bet <= 0:
        return await reply(content="Bahis 1 veya daha fazla olmali.", ephemeral=True)
    if not economy.take_money(user_id, bet):
        return await reply(
            content=f"Yetersiz bakiye ({economy.balance(user_id):,})", ephemeral=True
        )

    game = BlackjackGame(user_id=user_id, bet=bet)
    _active_bj[user_id] = game
    schedule_sync()

    if is_blackjack(game.player):
        game.stand()
        pay = game.resolve_payout()
        if pay > 0:
            economy.add_money(user_id, pay)
        _active_bj.pop(user_id, None)
        net = pay - bet
        bal = economy.balance(user_id)
        pv, dv = hand_value(game.player), hand_value(game.dealer)
        base = (
            f"💰 **Bahis:** {bet:,} | **Bakiye:** {bal:,}\n"
            f"🎩 **Kurpiyer:** {dv}\n"
            f"🃏 **Senin elin:** {pv}"
        )
        e = discord.Embed(
            title=f"🃏 {game.outcome()[0]}",
            description=f"{base}\n\n{'+' if net >= 0 else ''}{net:,}",
            color=0x57F287 if net >= 0 else 0xED4245,
        )
        e.set_image(url="attachment://blackjack.png")
        schedule_sync()
        return await reply(
            embed=e,
            file=bj_table_file(
                game.player,
                game.dealer,
            ),
        )

    view = BJView(game)
    e = view.embed()
    await reply(embed=e, view=view, file=view._table())


async def run_horse_race(i: discord.Interaction, slot: int, bet: int) -> None:
    uid = i.user.id
    if uid in _active_race:
        return await i.response.send_message(
            "Zaten bir yarisin devam ediyor.", ephemeral=True
        )
    if uid in _active_bj:
        return await i.response.send_message(
            "Once blackjack elini bitir.", ephemeral=True
        )
    if not is_open(uid):
        return await i.response.send_message(
            f"Once `/ciftlikac` ile ciftlik ac (**{STABLE_COST:,}**).", ephemeral=True
        )

    horse = get_owned_horse(uid, slot)
    if horse is None:
        return await i.response.send_message(
            "Gecersiz at numarasi. `/ciftlik` ile atlarini gor.", ephemeral=True
        )
    if bet <= 0:
        return await i.response.send_message("Bahis 1+", ephemeral=True)
    if not economy.take_money(uid, bet):
        return await i.response.send_message(
            f"Yetersiz bakiye ({economy.balance(uid):,})", ephemeral=True
        )
    schedule_sync()

    player = owned_to_racer(horse)
    npcs = random_npc_racers(5)
    racers = [player] + npcs

    _active_race.add(uid)
    await i.response.defer()

    positions = init_positions(racers)
    emb = race_embed(
        racers,
        positions,
        title="🏁 Ciftlik Ati Yarisi!",
        footer=f"Bahsin: {bet:,} | {player.emoji} {player.name} (x{player.odds:g})",
    )
    msg = await i.followup.send(embed=emb, wait=True)

    try:
        while max(positions.values()) < 100:
            await asyncio.sleep(0.85)
            tick(positions, racers)
            emb = race_embed(
                racers,
                positions,
                footer=f"Bahsin: {bet:,} | {player.emoji} {player.name}",
            )
            await msg.edit(embed=emb)

        win_r = winner(positions, racers)
        won = win_r.is_player
        pay = race_payout(bet, player, won)
        if pay > 0:
            economy.add_money(uid, pay)
        record_race(uid, player.horse_uid, won)
        bal = economy.balance(uid)
        net = pay - bet

        if won:
            title = f"🏆 {player.name} birinci oldu!"
            color = 0x57F287
            result = f"+{net:,} (x{player.odds:g}) | Bakiye **{bal:,}**"
        else:
            title = f"😢 Kaybettin. Birinci: {win_r.emoji} {win_r.name}"
            color = 0xED4245
            result = f"-{bet:,} | Bakiye **{bal:,}**"

        emb = race_embed(racers, positions, title=title, footer=result, color=color)
        await msg.edit(embed=emb)
        schedule_sync()
    finally:
        _active_race.discard(uid)


# --- Slash komutlar ---


@client.tree.command(name="para", description="Bakiyeni goster")
async def cmd_para(i: discord.Interaction):
    b = economy.balance(i.user.id)
    await i.response.send_message(f"Bakiyen: **{b:,}**")


@client.tree.command(name="maas", description="24 saatte bir maas al")
async def cmd_maas(i: discord.Interaction):
    ok, bal, wait = economy.claim_salary(i.user.id)
    if ok:
        await i.response.send_message(
            f"Maas **{DAILY_SALARY:,}** yatti. Bakiye: **{bal:,}**"
        )
        schedule_sync()
    else:
        await i.response.send_message(
            f"Maas aldin. Tekrar: **{fmt_time(wait)}** | Bakiye: **{bal:,}**"
        )


@client.tree.command(name="gonder", description="Baskasina para gonder")
@app_commands.describe(kisi="Alici", miktar="Miktar")
async def cmd_gonder(i: discord.Interaction, kisi: discord.Member, miktar: int):
    if kisi.bot:
        return await i.response.send_message("Bota gonderemezsin.", ephemeral=True)
    if kisi.id == i.user.id:
        return await i.response.send_message("Kendine gonderemezsin.", ephemeral=True)
    if miktar <= 0:
        return await i.response.send_message("Gecersiz miktar.", ephemeral=True)
    if not economy.take_money(i.user.id, miktar):
        return await i.response.send_message("Yetersiz bakiye.", ephemeral=True)
    economy.add_money(kisi.id, miktar)
    schedule_sync()
    await i.response.send_message(
        f"**{miktar:,}** -> {kisi.mention} | Senin bakiye: **{economy.balance(i.user.id):,}**"
    )


@client.tree.command(name="bj", description="Blackjack oyna")
@app_commands.describe(bahis="Bahis")
async def cmd_bj(i: discord.Interaction, bahis: int):
    async def reply(content=None, file=None, **kw):
        if file is not None:
            kw["file"] = file
        await i.response.send_message(content, **kw)

    await play_bj(i.user.id, bahis, reply)


@client.tree.command(name="ciftlik", description="Ciftligini ve atlarini goster")
async def cmd_ciftlik(i: discord.Interaction):
    desc, footer = stable_embed_text(i.user.id)
    emb = discord.Embed(title="🌾 Ciftligin", description=desc, color=0x27AE60)
    if footer:
        emb.set_footer(text=footer)
    await i.response.send_message(embed=emb)


@client.tree.command(name="topla", description="Ciftlikten pasif geliri topla")
async def cmd_topla(i: discord.Interaction):
    ok, msg, _ = collect_income(i.user.id)
    color = 0x57F287 if ok else 0xFEE75C
    emb = discord.Embed(
        title="💰 Pasif Gelir" if ok else "⏳ Henuz hazir degil",
        description=msg,
        color=color,
    )
    if ok and is_open(i.user.id):
        emb.set_footer(text=f"Saatlik: {total_income_per_hour(i.user.id):,}/saat")
    await i.response.send_message(embed=emb, ephemeral=not ok)
    if ok:
        schedule_sync()


@client.tree.command(name="ciftlikac", description="Ciftlik ac ve at almaya basla")
async def cmd_ciftlikac(i: discord.Interaction):
    ok, msg = open_stable(i.user.id)
    color = 0x57F287 if ok else 0xED4245
    await i.response.send_message(msg, ephemeral=not ok)
    if ok:
        schedule_sync()
        await i.followup.send(
            f"`/atpazar` → `/atsatin` → `/topla` ile pasif gelir.\nBakiye: **{economy.balance(i.user.id):,}**"
        )


@client.tree.command(name="atpazar", description="Satilik atlar ve ozellikleri")
async def cmd_atpazar(i: discord.Interaction):
    emb = discord.Embed(
        title="🏇 At Pazari",
        description=market_text(),
        color=0xE67E22,
    )
    emb.set_footer(text="Pasif gelir cinsine gore | /atsatin cins:arap")
    await i.response.send_message(embed=emb)


@client.tree.command(name="atsatin", description="Ciftligine at satin al")
@app_commands.describe(
    cins="At cinsi (atpazar listesi)",
    isim="Atina isim ver (istege bagli)",
)
@app_commands.choices(
    cins=[
        app_commands.Choice(name=f"{b['label']} — {b['price']:,}", value=kid)
        for kid, b in BREEDS.items()
    ]
)
async def cmd_atsatin(
    i: discord.Interaction,
    cins: app_commands.Choice[str],
    isim: str | None = None,
):
    ok, msg = buy_horse(i.user.id, cins.value, isim)
    await i.response.send_message(
        msg,
        ephemeral=not ok,
    )
    if ok:
        schedule_sync()
        await i.followup.send(f"Bakiye: **{economy.balance(i.user.id):,}**")


@client.tree.command(name="atyarisi", description="Kendi atinla yaris")
@app_commands.describe(at="Ciftligindeki at numarasi (1, 2, ...)", bahis="Bahis")
async def cmd_atyarisi(i: discord.Interaction, at: int, bahis: int):
    await run_horse_race(i, at, bahis)


@client.tree.command(name="siralama", description=f"En zengin {TOP_COUNT} kisi")
async def cmd_siralama(i: discord.Interaction):
    await i.response.defer()
    if i.guild:
        await sync_top1_role(i.guild)
    emb = await leaderboard_embed(i.user.id, i.guild)
    await i.followup.send(embed=emb)


@client.tree.command(name="paraver", description="[Sahip] Birine para ver")
@app_commands.describe(kisi="Kisi", miktar="Miktar")
async def cmd_paraver(i: discord.Interaction, kisi: discord.User, miktar: int):
    if not is_owner(i.user.id):
        return await i.response.send_message("Sadece bot sahibi.", ephemeral=True)
    if kisi.bot:
        return await i.response.send_message("Bota veremezsin.", ephemeral=True)
    if miktar <= 0:
        return await i.response.send_message("Gecersiz miktar.", ephemeral=True)
    economy.add_money(kisi.id, miktar)
    schedule_sync()
    await i.response.send_message(
        f"**{miktar:,}** -> {kisi.mention} | Yeni bakiye: **{economy.balance(kisi.id):,}**"
    )


@client.tree.command(name="yardim", description="Komut listesi")
async def cmd_yardim(i: discord.Interaction):
    h = SALARY_COOLDOWN_SEC // 3600
    emb = discord.Embed(title="Komutlar", color=0x5865F2)
    emb.add_field(
        name="Ekonomi",
        value=(
            "`/para` bakiye\n"
            f"`/maas` {h} saatte {DAILY_SALARY:,}\n"
            "`/gonder` transfer\n"
            f"`/siralama` top {TOP_COUNT}"
        ),
        inline=False,
    )
    emb.add_field(
        name="Ciftlik (pasif gelir)",
        value=(
            f"`/ciftlikac` ac ({STABLE_COST:,})\n"
            "`/atpazar` `/atsatin` at al\n"
            "`/ciftlik` `/topla` gelir topla\n"
            "`/atyarisi` (istege bagli yaris)"
        ),
        inline=False,
    )
    emb.add_field(
        name="Diger Oyun",
        value="`/bj` blackjack",
        inline=False,
    )
    emb.set_footer(text=f"Baslangic parasi: {START_BALANCE:,}")
    if is_owner(i.user.id):
        emb.add_field(name="Sahip", value="`/paraver` `/yenile`", inline=False)
    await i.response.send_message(embed=emb)


@client.tree.command(name="yenile", description="[Sahip] Slash komutlari yeniden yukle")
async def cmd_yenile(i: discord.Interaction):
    if not is_owner(i.user.id):
        return await i.response.send_message("Sadece bot sahibi.", ephemeral=True)
    await i.response.defer(ephemeral=True)
    names = await sync_slash_commands(client)
    if names:
        await i.followup.send(
            f"**{len(names)}** komut yuklendi:\n" + ", ".join(f"`/{n}`" for n in names),
            ephemeral=True,
        )
    else:
        await i.followup.send(
            "Komut yuklenemedi. Terminaldeki hataya bak veya `.env` DISCORD_GUILD_ID kontrol et.",
            ephemeral=True,
        )


@client.tree.error
async def tree_error(i: discord.Interaction, err: app_commands.AppCommandError):
    msg = f"Hata: {err}"
    if i.response.is_done():
        await i.followup.send(msg, ephemeral=True)
    else:
        await i.response.send_message(msg, ephemeral=True)


def main() -> None:
    token = get_token()
    ok, msg = check_token(token)
    print(msg)
    if not ok:
        print(f"\n.env yolu: {__import__('settings').ENV_PATH}")
        print("Ornek: DISCORD_TOKEN=Bot_sekmesinden_aldigin_token")
        sys.exit(1)

    gid = get_guild_id()
    if not gid.isdigit():
        print()
        print("=" * 50)
        print("ONEMLI: Komutlar icin .env dosyasina sunucu ID ekle:")
        print("  DISCORD_GUILD_ID=123456789012345678")
        print("Sunucuya sag tik -> Sunucu Kimligini Kopyala")
        print("Botu sunucuya applications.commands izniyle ekle!")
        print("=" * 50)

    client.run(token)


if __name__ == "__main__":
    main()
