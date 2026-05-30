# Discord Ekonomi Botu (sifirdan)

Slash komutlar: **Message Content Intent gerekmez.**

## Kurulum

1. https://discord.com/developers/applications -> Bot -> **Reset Token**
2. OAuth2 URL: scopes `bot` + `applications.commands`
3. `pip install -r requirements.txt`
4. `.env.example` -> `.env` kopyala, token ve sunucu ID yaz

```
DISCORD_TOKEN=bot_token_buraya
DISCORD_GUILD_ID=sunucu_id_buraya
```

5. `python token_kontrol.py` -> "Token gecerli" gormeli
6. `python bot.py`

## Komutlar

| Komut | Aciklama |
|--------|----------|
| `/para` | Bakiye |
| `/maas` | 24 saatte 500 |
| `/bj` | Blackjack |
| `/gonder` | Transfer |
| `/siralama` | Top 10 |
| `/paraver` | Sahip: para ver |
| `/yardim` | Liste |

Sahip ID: `1324038081896251415` (`.env` ile degistirilebilir)

## Token hatasi

`401` = Discord token gecersiz. **Client Secret degil**, Bot sekmesindeki token kullan.
