"""Bot ayarlari ve token okuma."""
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
DATA_DIR = BASE_DIR / "data"
DATA_FILE = DATA_DIR / "economy.json"

# Ekonomi
START_BALANCE = 1_000
DAILY_SALARY = 500
SALARY_COOLDOWN_SEC = 24 * 60 * 60
TOP_COUNT = 10

# Sahip
OWNER_ID = int(os.environ.get("BOT_OWNER_ID", "1324038081896251415"))


def _clean(value: str) -> str:
    for ch in "\r\n\ufeff\u200b":
        value = value.replace(ch, "")
    value = value.strip().strip('"').strip("'")
    if value.lower().startswith("bot "):
        value = value[4:].strip()
    return value


def load_env_file() -> dict[str, str]:
    if not ENV_PATH.is_file():
        return {}
    for enc in ("utf-8-sig", "utf-8", "utf-16", "utf-16-le"):
        try:
            text = ENV_PATH.read_text(encoding=enc)
            break
        except UnicodeError:
            continue
    else:
        return {}

    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        out[key.strip().upper()] = _clean(val)
    return out


def get_token() -> str:
    env = load_env_file()
    return _clean(env.get("DISCORD_TOKEN", os.environ.get("DISCORD_TOKEN", "")))


def get_guild_id() -> str:
    env = load_env_file()
    return _clean(env.get("DISCORD_GUILD_ID", os.environ.get("DISCORD_GUILD_ID", "")))


def check_token(token: str) -> tuple[bool, str]:
    if not token:
        return False, "Token bos — .env dosyasinda DISCORD_TOKEN=... olmali"
    req = urllib.request.Request(
        "https://discord.com/api/v10/users/@me",
        headers={
            "Authorization": f"Bot {token}",
            "User-Agent": "DiscordBot (https://github.com/discord/discord-api-docs)",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            return True, f"Token gecerli (@{data.get('username', '?')})"
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return (
                False,
                "Token gecersiz (401). Bot -> Reset Token, .env guncelle.",
            )
        if e.code == 403:
            return (
                False,
                "Erisim reddedildi (403). Bot hesabi kapali olabilir veya yanlis token turu.",
            )
        return False, f"Discord API hata: {e.code}"
    except Exception as e:
        return False, f"Baglanti hatasi: {e}"
