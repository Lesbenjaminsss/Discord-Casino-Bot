"""Blackjack masasi gorseli (Pillow)."""
from __future__ import annotations

import io
from typing import Sequence

from PIL import Image, ImageDraw, ImageFont

Card = tuple[str, str]

W, H = 480, 720
CARD_W, CARD_H = 112, 156
BRAND = "Les"
DEALER_Y = 52
PLAYER_Y = H - CARD_H - 52

RED_SUITS = {"♥", "♦"}


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    names = (
        ["arialbd.ttf", "Arial Bold.ttf", "segoeuib.ttf"]
        if bold
        else ["arial.ttf", "Arial.ttf", "segoeui.ttf"]
    )
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _felt_background() -> Image.Image:
    img = Image.new("RGB", (W, H), (18, 72, 48))
    draw = ImageDraw.Draw(img)
    for y in range(H):
        t = y / H
        g = int(22 + (48 - 22) * t)
        draw.line([(0, y), (W, y)], fill=(12, g, 38))
    draw.rectangle([8, 8, W - 8, H - 8], outline=(8, 40, 28), width=3)
    draw.rectangle([16, 16, W - 16, H - 16], outline=(30, 100, 60), width=2)
    return img


def _draw_label(img: Image.Image, text: str, y: int) -> None:
    draw = ImageDraw.Draw(img)
    bbox = draw.textbbox((0, 0), text, font=_font(15, True))
    tw = bbox[2] - bbox[0]
    draw.text(((W - tw) // 2, y), text, fill=(180, 220, 180), font=_font(15, True))


def _draw_card(
    base: Image.Image,
    xy: tuple[int, int],
    card: Card | None,
    hidden: bool = False,
) -> None:
    x, y = xy
    layer = Image.new("RGBA", (CARD_W, CARD_H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)

    if hidden or card is None:
        d.rounded_rectangle([0, 0, CARD_W - 1, CARD_H - 1], radius=12, fill=(35, 75, 140))
        d.rounded_rectangle([6, 6, CARD_W - 7, CARD_H - 7], radius=10, outline=(90, 140, 220), width=2)
        d.text((CARD_W // 2 - 10, CARD_H // 2 - 14), "?", fill=(200, 220, 255), font=_font(34, True))
    else:
        rank, suit = card
        d.rounded_rectangle([0, 0, CARD_W - 1, CARD_H - 1], radius=12, fill=(250, 250, 248))
        d.rounded_rectangle([2, 2, CARD_W - 3, CARD_H - 3], radius=11, outline=(180, 180, 175), width=1)
        color = (200, 40, 50) if suit in RED_SUITS else (25, 25, 30)
        d.text((12, 10), rank, fill=color, font=_font(30, True))
        d.text((12, 42), suit, fill=color, font=_font(26, True))
        big = _font(52, True)
        bbox = d.textbbox((0, 0), suit, font=big)
        sw, sh = bbox[2] - bbox[0], bbox[3] - bbox[1]
        d.text(((CARD_W - sw) // 2, (CARD_H - sh) // 2 - 4), suit, fill=color, font=big)
        d.text((CARD_W - 40, CARD_H - 68), rank, fill=color, font=_font(24, True))
        d.text((CARD_W - 36, CARD_H - 40), suit, fill=color, font=_font(21, True))

    base.paste(layer, (x, y), layer)


def _fan_positions(n: int, y: int) -> list[tuple[int, int]]:
    if n <= 0:
        return []
    overlap = 44
    total_w = CARD_W + overlap * (n - 1)
    start_x = (W - total_w) // 2
    return [(start_x + i * overlap, y) for i in range(n)]


def _draw_brand(img: Image.Image, y: int) -> None:
    draw = ImageDraw.Draw(img)
    font = _font(56, True)
    bbox = draw.textbbox((0, 0), BRAND, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (W - tw) // 2
    for ox, oy in [(-2, 2), (2, 2)]:
        draw.text((x + ox, y + oy), BRAND, fill=(20, 20, 25), font=font)
    draw.text((x, y), BRAND, fill=(230, 235, 245), font=font)


def render_blackjack_image(
    player: Sequence[Card],
    dealer: Sequence[Card],
    *,
    hide_dealer_first: bool = False,
) -> io.BytesIO:
    img = _felt_background()

    _draw_label(img, "Kurpiyerin eli", DEALER_Y - 22)
    for (x, y), i, card in zip(
        _fan_positions(len(dealer), DEALER_Y),
        range(len(dealer)),
        dealer,
    ):
        hidden = hide_dealer_first and i == 0
        _draw_card(img, (x, y), card, hidden=hidden)

    brand_y = (DEALER_Y + CARD_H + PLAYER_Y) // 2 - 28
    _draw_brand(img, brand_y)

    _draw_label(img, "Senin elin", PLAYER_Y - 22)
    for (x, y), card in zip(_fan_positions(len(player), PLAYER_Y), player):
        _draw_card(img, (x, y), card)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf


def discord_file(
    player: Sequence[Card],
    dealer: Sequence[Card],
    *,
    hide_dealer_first: bool = False,
):
    import discord

    buf = render_blackjack_image(
        player,
        dealer,
        hide_dealer_first=hide_dealer_first,
    )
    return discord.File(buf, filename="blackjack.png")
