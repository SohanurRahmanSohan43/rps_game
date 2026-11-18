"""In-game chat: what a message may contain, and how fast messages may flow.

A chat message from the other player is untrusted text that ends up drawn in
your terminal, so it gets the same treatment as a name: only letters, numbers,
punctuation, symbols and emoji; no control characters, no escape sequences, no
bidi overrides, no line breaks. Both sides run this very check, so an honest
game never sends something the other would refuse.
"""
from __future__ import annotations

import re
import time
import unicodedata
from dataclasses import dataclass
from typing import Callable, Optional

MAX_CHAT_CHARS = 200

# Sending: a short burst is fine, then roughly one message every two seconds.
SEND_BURST = 5
SEND_REFILL_PER_SECOND = 0.5
# Receiving is deliberately more generous than sending, so a well-behaved opponent
# is never dropped; only a flooder is.
RECV_BURST = 8
RECV_REFILL_PER_SECOND = 1.0
FLOOD_DROPS_BEFORE_MUTE = 20
FLOOD_WINDOW_SECONDS = 60.0

_JOINERS = {"\u200c", "\u200d"}          # needed inside words in several scripts, and in emoji
_SPACES = re.compile(" {2,}")


@dataclass(frozen=True)
class ChatCheck:
    text: str
    error: Optional[str]

    @property
    def ok(self) -> bool:
        return self.error is None


def check_chat(raw: str) -> ChatCheck:
    """Tidy and validate one message. ``text`` is the tidy form when ``ok``."""
    text = unicodedata.normalize("NFC", raw)
    if any(ch.isspace() and ch != " " for ch in text):
        return ChatCheck("", "Messages can't contain tabs or line breaks.")
    text = _SPACES.sub(" ", text).strip(" ")
    if not text:
        return ChatCheck("", "Type a message first.")
    for ch in text:
        if ch == " " or ch in _JOINERS or unicodedata.category(ch)[0] in "LMNPS":
            continue
        return ChatCheck("", "Messages can only contain letters, numbers, punctuation, "
                             "symbols and emoji.")
    if len(text) > MAX_CHAT_CHARS:
        return ChatCheck("", f"Messages can be at most {MAX_CHAT_CHARS} characters.")
    return ChatCheck(text, None)


def chat_error(raw: str) -> Optional[str]:
    return check_chat(raw).error


class TokenBucket:
    """Allows bursts up to ``capacity``, refilling at ``per_second`` afterwards."""

    def __init__(self, capacity: float, per_second: float,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._capacity, self._rate, self._clock = float(capacity), per_second, clock
        self._tokens = float(capacity)
        self._last = clock()

    def allow(self) -> bool:
        now = self._clock()
        self._tokens = min(self._capacity, self._tokens + (now - self._last) * self._rate)
        self._last = now
        if self._tokens >= 1.0:
            self._tokens -= 1.0
            return True
        return False
