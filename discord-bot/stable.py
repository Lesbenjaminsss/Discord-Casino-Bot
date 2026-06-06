"""Ciftlik / ahir — at sahipligi ve ozellikler."""
from __future__ import annotations

import random
import time
import uuid
from dataclasses import dataclass
from typing import Any

import economy
from storage import load_all, save_all

STABLE_COST = 2_000
MAX_HORSES = 8
MAX_PASSIVE_HOURS = 24  # En fazla 24 saat birikir

# cins_id -> sablon
BREEDS: dict[str, dict[str, Any]] = {
    "midilli": {
        "emoji": "🐴",
        "label": "Midilli",
        "price": 600,
        "income_hour": 18,
        "speed": 55,
        "stamina": 50,
        "luck": 70,
        "desc": "Ucuz pasif gelir",
    },
    "arap": {
        "emoji": "🐎",
        "label": "Arap Ati",
        "price": 1_200,
        "income_hour": 40,
        "speed": 78,
        "stamina": 72,
        "luck": 65,
        "desc": "Dengeli kazanc",
    },
    "ingiliz": {
        "emoji": "🏇",
        "label": "Ingiliz Thoroughbred",
        "price": 2_000,
        "income_hour": 65,
        "speed": 88,
        "stamina": 68,
        "luck": 58,
        "desc": "Yuksek saatlik gelir",
    },
    "friz": {
        "emoji": "🦄",
        "label": "Friz Ati",
        "price": 1_500,
        "income_hour": 52,
        "speed": 62,
        "stamina": 90,
        "luck": 55,
        "desc": "Dayanikli uretim",
    },
    "safkan": {
        "emoji": "⚡",
        "label": "Safkan Sampiyon",
        "price": 4_000,
        "income_hour": 110,
        "speed": 92,
        "stamina": 85,
        "luck": 75,
        "desc": "En iyi pasif gelir",
    },
}

NPC_POOL = [
    ("Ruzgar", "💨", 70, 65, 60),
    ("Ates", "🔥", 75, 60, 55),
    ("Yildiz", "⭐", 68, 70, 65),
    ("Kartal", "🦅", 80, 55, 50),
    ("Simsek", "⚡", 85, 58, 52),
    ("Pamuk", "☁️", 50, 75, 80),
]


def _save_user(user_id: int, user: dict[str, Any]) -> None:
    data = load_all()
    data[str(user_id)] = user
    save_all(data)


def _stable(user_id: int) -> dict[str, Any]:
    u = economy.ensure(user_id)
    if "stable" not in u:
        u["stable"] = {"open": False, "horses": [], "last_collect": int(time.time())}
        _save_user(user_id, u)
    st = u["stable"]
    if "last_collect" not in st:
        st["last_collect"] = int(time.time())
        u["stable"] = st
        _save_user(user_id, u)
    return st


def is_open(user_id: int) -> bool:
    return bool(_stable(user_id).get("open"))


def open_stable(user_id: int) -> tuple[bool, str]:
    if is_open(user_id):
        return False, "Ciftligin zaten acik."
    if not economy.take_money(user_id, STABLE_COST):
        return False, f"Yetersiz bakiye. Acilis: **{STABLE_COST:,}**"
    u = economy.ensure(user_id)
    u["stable"] = {"open": True, "horses": [], "last_collect": int(time.time())}
    _save_user(user_id, u)
    return True, f"Ciftlik acildi! (**-{STABLE_COST:,}**) Atlar saatlik pasif gelir uretir."


def calc_odds(speed: int, stamina: int, luck: int) -> float:
    """Ozelliklere gore bahis orani — guclu at dusuk oran."""
    power = speed * 0.45 + stamina * 0.35 + luck * 0.20
    power = max(35.0, min(95.0, power))
    odds = 100.0 / power * 2.0
    return round(max(1.3, min(12.0, odds)), 1)


def _roll_stat(base: int, spread: int = 6) -> int:
    return max(30, min(99, base + random.randint(-spread, spread)))


def buy_horse(user_id: int, breed_id: str, custom_name: str | None = None) -> tuple[bool, str]:
    if not is_open(user_id):
        return False, "Once `/ciftlikac` ile ciftlik ac."
    breed = BREEDS.get(breed_id)
    if not breed:
        return False, "Gecersiz cins. `/atpazar` ile listeye bak."
    st = _stable(user_id)
    if len(st["horses"]) >= MAX_HORSES:
        return False, f"Maksimum **{MAX_HORSES}** at sahibi olabilirsin."
    price = int(breed["price"])
    if not economy.take_money(user_id, price):
        return False, f"Yetersiz bakiye. Fiyat: **{price:,}**"

    speed = _roll_stat(breed["speed"])
    stamina = _roll_stat(breed["stamina"])
    luck = _roll_stat(breed["luck"])
    name = (custom_name or breed["label"]).strip()[:20] or breed["label"]
    horse = {
        "uid": uuid.uuid4().hex[:8],
        "breed": breed_id,
        "name": name,
        "emoji": breed["emoji"],
        "speed": speed,
        "stamina": stamina,
        "luck": luck,
        "odds": calc_odds(speed, stamina, luck),
        "wins": 0,
        "races": 0,
    }
    st["horses"].append(horse)
    u = economy.ensure(user_id)
    u["stable"] = st
    _save_user(user_id, u)
    inc = breed_income_hour(breed_id)
    return True, (
        f"{horse['emoji']} **{name}** satin alindi! (**-{price:,}**)\n"
        f"Pasif gelir: **{inc}/saat** | Hiz {speed} | Day. {stamina} | Sans {luck}\n"
        f"Yaris orani: **x{horse['odds']}** — `/topla` ile gelir topla"
    )


def list_horses(user_id: int) -> list[dict[str, Any]]:
    return list(_stable(user_id).get("horses", []))


def get_owned_horse(user_id: int, slot: int) -> dict[str, Any] | None:
    horses = list_horses(user_id)
    if slot < 1 or slot > len(horses):
        return None
    return horses[slot - 1]


def record_race(user_id: int, horse_uid: str, won: bool) -> None:
    u = economy.ensure(user_id)
    st = u.get("stable", {"open": False, "horses": []})
    for h in st.get("horses", []):
        if h["uid"] == horse_uid:
            h["races"] = int(h.get("races", 0)) + 1
            if won:
                h["wins"] = int(h.get("wins", 0)) + 1
            break
    u["stable"] = st
    _save_user(user_id, u)


def breed_income_hour(breed_id: str) -> int:
    return int(BREEDS.get(breed_id, {}).get("income_hour", 0))


def total_income_per_hour(user_id: int) -> int:
    if not is_open(user_id):
        return 0
    total = 0
    for h in list_horses(user_id):
        total += breed_income_hour(h.get("breed", ""))
    return total


def pending_income(user_id: int) -> tuple[int, int]:
    """(biriken miktar, saniye gecti)"""
    if not is_open(user_id):
        return 0, 0
    horses = list_horses(user_id)
    if not horses:
        return 0, 0
    st = _stable(user_id)
    last = int(st.get("last_collect", int(time.time())))
    elapsed = int(time.time() - last)
    elapsed = min(elapsed, MAX_PASSIVE_HOURS * 3600)
    if elapsed < 60:
        return 0, elapsed
    per_hour = total_income_per_hour(user_id)
    amount = int(per_hour * (elapsed / 3600))
    return max(0, amount), elapsed


def collect_income(user_id: int) -> tuple[bool, str, int]:
    amount, elapsed = pending_income(user_id)
    if not is_open(user_id):
        return False, "Once `/ciftlikac` ile ciftlik ac.", 0
    if not list_horses(user_id):
        return False, "At yok. `/atsatin` ile at al.", 0
    if amount < 1:
        return (
            False,
            f"Henuz biriken gelir yok. Toplam **{total_income_per_hour(user_id):,}**/saat uretiyorsun.",
            0,
        )
    economy.add_money(user_id, amount)
    st = _stable(user_id)
    st["last_collect"] = int(time.time())
    u = economy.ensure(user_id)
    u["stable"] = st
    _save_user(user_id, u)
    bal = economy.balance(user_id)
    hours = elapsed // 3600
    mins = (elapsed % 3600) // 60
    time_txt = f"{hours}s {mins}dk" if hours else f"{mins} dk"
    return (
        True,
        f"**+{amount:,}** pasif gelir toplandi! ({time_txt})\nBakiye: **{bal:,}**",
        amount,
    )


def market_text() -> str:
    lines = []
    for bid, b in BREEDS.items():
        o = calc_odds(b["speed"], b["stamina"], b["luck"])
        inc = b["income_hour"]
        lines.append(
            f"{b['emoji']} **{b['label']}** (`{bid}`) — **{b['price']:,}**\n"
            f"  Pasif: **{inc}/saat** | Hiz {b['speed']} | ~yaris x{o}\n"
            f"  _{b['desc']}_"
        )
    return "\n".join(lines)


def stable_embed_text(user_id: int) -> tuple[str, str | None]:
    """(aciklama, footer)"""
    if not is_open(user_id):
        return f"Ciftlik kapali. `/ciftlikac` ile ac (**{STABLE_COST:,}**)", None
    horses = list_horses(user_id)
    per_h = total_income_per_hour(user_id)
    pending, _ = pending_income(user_id)
    header = f"Saatlik gelir: **{per_h:,}**/saat | Biriken: **{pending:,}**\n`/topla` ile topla\n\n"
    if not horses:
        return header + f"Ciftligin bos. `/atsatin` ile at al. (max {MAX_HORSES})", None
    lines = [header]
    for i, h in enumerate(horses, 1):
        wr = h.get("wins", 0)
        rc = h.get("races", 0)
        inc = breed_income_hour(h.get("breed", ""))
        lines.append(
            f"**{i}.** {h['emoji']} **{h['name']}** — **{inc}/saat**\n"
            f"  Hiz {h['speed']} | Day. {h['stamina']} | Sans {h['luck']} | Yaris x{h['odds']} | G: {wr}/{rc}"
        )
    footer = f"Max {MAX_PASSIVE_HOURS} saat birikir | /atyarisi ile yaris"
    return "\n".join(lines), footer


@dataclass
class Racer:
    key: str
    name: str
    emoji: str
    speed: int
    stamina: int
    luck: int
    odds: float
    is_player: bool = False
    horse_uid: str = ""


def owned_to_racer(horse: dict[str, Any]) -> Racer:
    return Racer(
        key=f"p_{horse['uid']}",
        name=horse["name"],
        emoji=horse["emoji"],
        speed=int(horse["speed"]),
        stamina=int(horse["stamina"]),
        luck=int(horse["luck"]),
        odds=float(horse["odds"]),
        is_player=True,
        horse_uid=horse["uid"],
    )


def random_npc_racers(count: int = 5) -> list[Racer]:
    picked = random.sample(NPC_POOL, min(count, len(NPC_POOL)))
    racers = []
    for i, (name, emoji, sp, st, lk) in enumerate(picked):
        sp, st, lk = _roll_stat(sp, 4), _roll_stat(st, 4), _roll_stat(lk, 4)
        racers.append(
            Racer(
                key=f"n_{i}",
                name=name,
                emoji=emoji,
                speed=sp,
                stamina=st,
                luck=lk,
                odds=calc_odds(sp, st, lk),
            )
        )
    return racers
