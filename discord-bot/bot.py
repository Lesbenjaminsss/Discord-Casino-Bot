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
from blackjack import BlackjackGame, hand_display, hand_value, is_blackjack
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


def fmt_time(sec: int) -> str:
    return str(timedelta(seconds=max(0, sec)))


def is_owner(uid: int) -> bool:
    return uid == OWNER_ID


class EcoBot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self) -> None:
        gid = get_guild_id()
        if gid.isdigit():
            guild = discord.Object(id=int(gid))
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            print(f"Komutlar sunucuya yuklendi ({len(synced)} adet, guild {gid})")
        else:
            synced = await self.tree.sync()
            print(f"Komutlar global yuklendi ({len(synced)} adet)")

    async def on_ready(self) -> None:
        print("=" * 50, flush=True)
        print("BOT AKTIF", flush=True)
        print(f"  {self.user} ({self.user.id})", flush=True)
        print("  Komutlar: /yardim /para /maas /bj /siralama /gonder", flush=True)
        if is_owner(self.user.id):
            print("  Sahip: /paraver", flush=True)
        print("=" * 50, flush=True)
        await self.change_presence(activity=discord.Game(name="/yardim"))


client = EcoBot()


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

    def embed(self, reveal: bool = False) -> discord.Embed:
        g = self.game
        pv = hand_value(g.player)
        title = "Blackjack"
        if g.finished:
            title = f"Blackjack — {g.outcome()[0]}"
        e = discord.Embed(title=title, color=0x2B2D31)
        e.add_field(name=f"Sen ({pv})", value=hand_display(g.player), inline=False)
        dv = hand_value(g.dealer) if reveal or g.finished else "?"
        e.add_field(
            name=f"Kurpiyer ({dv})",
            value=hand_display(g.dealer, hide_first=not reveal and not g.finished),
            inline=False,
        )
        e.set_footer(text=f"Bahis: {g.bet:,}")
        return e

    async def finish(self, i: discord.Interaction) -> None:
        g = self.game
        pay = g.resolve_payout()
        if pay > 0:
            economy.add_money(g.user_id, pay)
        net = pay - g.bet
        bal = economy.balance(g.user_id)
        e = self.embed(reveal=True)
        if net > 0:
            e.color, e.description = 0x57F287, f"+{net:,} | Bakiye **{bal:,}**"
        elif net == 0:
            e.color, e.description = 0xFEE75C, f"Bahis iade | Bakiye **{bal:,}**"
        else:
            e.color, e.description = 0xED4245, f"-{g.bet:,} | Bakiye **{bal:,}**"
        for c in self.children:
            c.disabled = True
        _active_bj.pop(g.user_id, None)
        await i.response.edit_message(embed=e, view=self)
        self.stop()

    @discord.ui.button(label="Kart cek", style=discord.ButtonStyle.primary)
    async def hit(self, i: discord.Interaction, _b: discord.ui.Button):
        if self.game.finished:
            return await i.response.defer()
        self.game.hit()
        if self.game.finished:
            return await self.finish(i)
        await i.response.edit_message(embed=self.embed(), view=self)

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

    if is_blackjack(game.player):
        game.stand()
        pay = game.resolve_payout()
        if pay > 0:
            economy.add_money(user_id, pay)
        _active_bj.pop(user_id, None)
        net = pay - bet
        e = discord.Embed(
            title=f"Blackjack — {game.outcome()[0]}",
            description=f"{'+' if net >= 0 else ''}{net:,} | Bakiye **{economy.balance(user_id):,}**",
            color=0x57F287 if net >= 0 else 0xED4245,
        )
        return await reply(embed=e)

    view = BJView(game)
    e = view.embed()
    e.description = "Kart cek veya dur."
    await reply(embed=e, view=view)


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
    await i.response.send_message(
        f"**{miktar:,}** -> {kisi.mention} | Senin bakiye: **{economy.balance(i.user.id):,}**"
    )


@client.tree.command(name="bj", description="Blackjack oyna")
@app_commands.describe(bahis="Bahis")
async def cmd_bj(i: discord.Interaction, bahis: int):
    async def reply(content=None, **kw):
        await i.response.send_message(content, **kw)

    await play_bj(i.user.id, bahis, reply)


@client.tree.command(name="siralama", description=f"En zengin {TOP_COUNT} kisi")
async def cmd_siralama(i: discord.Interaction):
    await i.response.defer()
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
        name="Oyun",
        value="`/bj` blackjack (bahis siniri yok, bakiyen kadar)",
        inline=False,
    )
    emb.set_footer(text=f"Baslangic parasi: {START_BALANCE:,}")
    if is_owner(i.user.id):
        emb.add_field(name="Sahip", value="`/paraver`", inline=False)
    await i.response.send_message(embed=emb)


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
        print("IPUCU: .env icine DISCORD_GUILD_ID=sunucu_id ekle -> komutlar aninda gelir")

    client.run(token)


if __name__ == "__main__":
    main()
