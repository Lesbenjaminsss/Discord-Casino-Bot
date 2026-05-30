import random
from dataclasses import dataclass, field

SUITS = ("♠", "♥", "♦", "♣")
RANKS = ("A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K")


def new_deck() -> list[tuple[str, str]]:
    deck = [(rank, suit) for suit in SUITS for rank in RANKS]
    random.shuffle(deck)
    return deck


def card_label(card: tuple[str, str]) -> str:
    rank, suit = card
    return f"`{rank}{suit}`"


def hand_display(cards: list[tuple[str, str]], hide_first: bool = False) -> str:
    if hide_first and cards:
        return f"`??` " + " ".join(card_label(c) for c in cards[1:])
    return " ".join(card_label(c) for c in cards)


def hand_value(cards: list[tuple[str, str]]) -> int:
    total = 0
    aces = 0
    for rank, _ in cards:
        if rank == "A":
            aces += 1
            total += 11
        elif rank in ("K", "Q", "J"):
            total += 10
        else:
            total += int(rank)
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total


def is_blackjack(cards: list[tuple[str, str]]) -> bool:
    return len(cards) == 2 and hand_value(cards) == 21


@dataclass
class BlackjackGame:
    user_id: int
    bet: int
    deck: list[tuple[str, str]] = field(default_factory=new_deck)
    player: list[tuple[str, str]] = field(default_factory=list)
    dealer: list[tuple[str, str]] = field(default_factory=list)
    finished: bool = False
    doubled: bool = False

    def __post_init__(self) -> None:
        self.player = [self._draw(), self._draw()]
        self.dealer = [self._draw(), self._draw()]

    def _draw(self) -> tuple[str, str]:
        if not self.deck:
            self.deck = new_deck()
        return self.deck.pop()

    def player_can_hit(self) -> bool:
        return not self.finished and hand_value(self.player) < 21

    def hit(self) -> int:
        if self.finished:
            return hand_value(self.player)
        self.player.append(self._draw())
        if hand_value(self.player) >= 21:
            self._finish()
        return hand_value(self.player)

    def stand(self) -> None:
        if self.finished:
            return
        self._finish()

    def _dealer_play(self) -> None:
        while hand_value(self.dealer) < 17:
            self.dealer.append(self._draw())

    def _finish(self) -> None:
        if self.finished:
            return
        self.finished = True
        self._dealer_play()

    def outcome(self) -> tuple[str, float]:
        """
        Sonuç metni ve çarpan.
        Çarpan: bahis üzerinden net kazanç (2 = ikiye katlama kazancı gibi düşünülebilir)
        Gerçek ödeme: bet * multiplier (multiplier negatif = kayıp)
        """
        pv = hand_value(self.player)
        dv = hand_value(self.dealer)

        if pv > 21:
            return "Battın (21'i geçtin).", -1.0

        if is_blackjack(self.player) and not is_blackjack(self.dealer):
            return "Blackjack! 🎉", 1.5

        if dv > 21:
            return "Kurpiyer battı, kazandın!", 1.0

        if pv > dv:
            return "Kazandın!", 1.0
        if pv < dv:
            return "Kurpiyer kazandı.", -1.0
        return "Berabere (push).", 0.0

    def resolve_payout(self) -> int:
        """Net para değişimi (bahis zaten düşüldü varsayımıyla geri ödeme)."""
        _, mult = self.outcome()
        if mult < 0:
            return 0
        if mult == 0:
            return self.bet
        if mult == 1.5:
            return int(self.bet * 2.5)
        return self.bet * 2
