import time
from typing import Any

from settings import DAILY_SALARY, SALARY_COOLDOWN_SEC, START_BALANCE
from storage import load_all, save_all


def _key(user_id: int) -> str:
    return str(user_id)


def _new_user() -> dict[str, Any]:
    return {"balance": START_BALANCE, "last_salary": 0}


def ensure(user_id: int) -> dict[str, Any]:
    data = load_all()
    k = _key(user_id)
    if k not in data:
        data[k] = _new_user()
        save_all(data)
    return data[k]


def balance(user_id: int) -> int:
    return int(ensure(user_id)["balance"])


def set_balance(user_id: int, amount: int) -> int:
    u = ensure(user_id)
    u["balance"] = max(0, int(amount))
    data = load_all()
    data[_key(user_id)] = u
    save_all(data)
    return u["balance"]


def add_money(user_id: int, amount: int) -> int:
    return set_balance(user_id, balance(user_id) + amount)


def take_money(user_id: int, amount: int) -> bool:
    if amount <= 0 or balance(user_id) < amount:
        return False
    set_balance(user_id, balance(user_id) - amount)
    return True


def claim_salary(user_id: int) -> tuple[bool, int, int]:
    u = ensure(user_id)
    last = int(u.get("last_salary", 0))
    wait = SALARY_COOLDOWN_SEC - (time.time() - last)
    if wait > 0:
        return False, balance(user_id), int(wait)
    u["balance"] = balance(user_id) + DAILY_SALARY
    u["last_salary"] = int(time.time())
    data = load_all()
    data[_key(user_id)] = u
    save_all(data)
    return True, u["balance"], 0


def all_sorted() -> list[tuple[int, int]]:
    rows: list[tuple[int, int]] = []
    for k, u in load_all().items():
        try:
            rows.append((int(k), int(u.get("balance", 0))))
        except ValueError:
            continue
    rows.sort(key=lambda x: x[1], reverse=True)
    return rows


def top(limit: int = 10) -> list[tuple[int, int]]:
    return all_sorted()[:limit]


def rank_of(user_id: int) -> tuple[int, int] | None:
    for i, (uid, bal) in enumerate(all_sorted(), start=1):
        if uid == user_id:
            return i, bal
    return None
