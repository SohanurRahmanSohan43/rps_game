import pytest

from rps_game import chat
from rps_game.chat import MAX_CHAT_CHARS, TokenBucket, check_chat, chat_error


@pytest.mark.parametrize("text", [
    "hello", "good game!", "1/2 of a pizza", "see https://example.com/x?y=1", "نص عربي",
    "সোহান, ভালো খেলা", "李雷 加油", "gg 😀", "family 👨\u200d👩\u200d👧", "naïve café", "100%", "a",
    "x" * MAX_CHAT_CHARS,
])
def test_ordinary_messages_are_accepted_unchanged(text):
    result = check_chat(text)
    assert result.ok and result.text == text


def test_messages_are_tidied():
    assert check_chat("  hello   there  ").text == "hello there"


@pytest.mark.parametrize("raw", ["", "   ", "\u200b"])
def test_empty_messages_are_refused(raw):
    assert not check_chat(raw).ok


@pytest.mark.parametrize("raw", [
    "line one\nline two", "tab\there", "carriage\rreturn", "no\u00a0break",
    "esc\x1b[31mred", "bell\x07", "nul\x00", "\u202egnp.exe",           # escape codes, bidi override
    "zero\u200bwidth", "\u2066isolate", "tag\U000e0041", "private\ue000use",
])
def test_anything_that_could_garble_a_terminal_is_refused(raw):
    assert not check_chat(raw).ok


def test_overlong_messages_are_refused_with_the_limit_in_the_text():
    assert f"at most {MAX_CHAT_CHARS}" in check_chat("x" * (MAX_CHAT_CHARS + 1)).error


def test_chat_error_helper():
    assert chat_error("hi") is None and chat_error("") is not None


def test_a_message_is_valid_after_tidying_if_and_only_if_both_sides_would_agree():
    """Whatever the sender tidies, the receiver's strict check accepts unchanged."""
    for raw in ["  a   b  ", "x", "ok  ok"]:
        tidy = check_chat(raw).text
        assert check_chat(tidy).text == tidy


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def test_token_bucket_allows_a_burst_then_throttles_then_refills():
    clock = Clock()
    bucket = TokenBucket(3, 1.0, clock)
    assert [bucket.allow() for _ in range(4)] == [True, True, True, False]
    clock.now += 1.0
    assert bucket.allow() and not bucket.allow()
    clock.now += 100
    assert sum(bucket.allow() for _ in range(10)) == 3                # never more than capacity


def test_receiving_is_more_generous_than_sending():
    assert chat.RECV_BURST > chat.SEND_BURST
    assert chat.RECV_REFILL_PER_SECOND > chat.SEND_REFILL_PER_SECOND
