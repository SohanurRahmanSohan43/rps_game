"""Chat and automatic reveals inside NetworkOpponent."""
import threading
import time

import pytest

from netutil import connected_pair, send
from rps_game import chat as chatmod
from rps_game.engine import Move
from rps_game.net import protocol as proto
from rps_game.net.errors import ProtocolError, Timeout
from rps_game.net.game import ChatLine, NetworkOpponent

R, P, S = Move.ROCK, Move.PAPER, Move.SCISSORS
SLOW = dict(ping_interval=60, first_ping_delay=60, liveness_timeout=600)


@pytest.fixture
def make():
    opened = []

    def factory(wrap=("host", "join"), host_opts=None, join_opts=None, **kw):
        host, join, box = connected_pair()
        h = NetworkOpponent(host, **{**SLOW, **kw, **(host_opts or {})}) if "host" in wrap else host
        j = NetworkOpponent(join, **{**SLOW, **kw, **(join_opts or {})}) if "join" in wrap else join
        opened.extend(x for x in (h, j) if isinstance(x, NetworkOpponent))
        return h, j, box

    yield factory
    for opp in opened:
        opp.close()


def wait_until(predicate, timeout=3.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def safe(fn):
    try:
        return fn()
    except BaseException as exc:                           # noqa: BLE001
        return exc


def in_thread(fn):
    out = []
    t = threading.Thread(target=lambda: out.append(safe(fn)), daemon=True)
    t.start()
    return t, out


# ============================================================ reveals happen automatically

def test_a_blocked_screen_cannot_make_the_other_player_time_out(make):
    """The host is stuck in a prompt (its wait-hook blocks for a second) while the joiner,
    who allows only half a second for a reveal, is waiting. The reveal goes out by itself."""
    h, j, _ = make(commit_timeout=5, reveal_timeout=0.5)
    first = []

    def blocking_hook(text):
        if not first:
            first.append(1)
            time.sleep(1.0)                                # "Leave the game?" sitting on screen
        return True

    h.on_wait = blocking_hook
    th, rh = in_thread(lambda: h.play(R))
    time.sleep(0.3)                                        # the host has committed and is now blocked
    tj, rj = in_thread(lambda: j.play(P))
    th.join(8); tj.join(8)
    assert rj == [R], rj                                   # the joiner got the host's move in time
    assert rh == [P], rh


def test_the_reveal_follows_the_second_commit_immediately_on_the_wire(make):
    frames = []
    h, j, box = make()
    box.tamper = lambda role, data: frames.append((role, type(proto.decode(data)).__name__)) or data
    th, _ = in_thread(lambda: h.play(R))
    tj, _ = in_thread(lambda: j.play(P))
    th.join(5); tj.join(5)
    kinds = [k for _, k in frames]
    assert kinds[:2] == ["Commit", "Commit"] and sorted(kinds[2:]) == ["Reveal", "Reveal"]


# ============================================================ sending and receiving

def test_a_message_arrives_marks_unread_and_previews(make):
    h, j, _ = make()
    assert h.send_chat("hello there") is None
    assert wait_until(lambda: j.chat_unread() == 1)
    assert j.chat_lines() == [ChatLine("them", "hello there")]
    assert h.chat_lines() == [ChatLine("me", "hello there")]
    assert j.chat_preview() == "hello there" and h.chat_preview() == ""
    j.chat_mark_read()
    assert j.chat_unread() == 0


def test_messages_flow_both_ways_in_order(make):
    h, j, _ = make()
    for text in ("one", "two", "three"):
        assert h.send_chat(text) is None
    assert j.send_chat("reply") is None
    assert wait_until(lambda: len(j.chat_lines()) == 4 and len(h.chat_lines()) == 4)
    lines = j.chat_lines()
    # each sender's own messages keep their order (how they interleave with mine is timing)
    assert [l.text for l in lines if l.sender == "them"] == ["one", "two", "three"]
    assert [l.text for l in lines if l.sender == "me"] == ["reply"]


def test_messages_are_tidied_before_sending(make):
    h, j, _ = make()
    assert h.send_chat("  hi    there  ") is None
    assert wait_until(lambda: j.chat_unread() == 1)
    assert j.chat_lines()[0].text == "hi there"


@pytest.mark.parametrize("raw, fragment", [("", "Type a message"), ("a\nb", "line breaks"),
                                           ("x" * 201, "at most 200"), ("\x1b[2J", "only contain")])
def test_invalid_messages_are_refused_locally_and_never_sent(make, raw, fragment):
    h, j, _ = make()
    assert fragment in h.send_chat(raw)
    time.sleep(0.1)
    assert j.chat_lines() == [] and h.chat_lines() == []


def test_unicode_messages_survive_the_trip(make):
    h, j, _ = make()
    assert h.send_chat("সোহান: ভালো খেলা 😀") is None
    assert wait_until(lambda: j.chat_unread() == 1)
    assert j.chat_preview() == "সোহান: ভালো খেলা 😀"


def test_chat_works_at_any_moment_including_between_commit_and_reveal(make):
    h, j, _ = make()
    th, rh = in_thread(lambda: h.play(R))
    time.sleep(0.1)
    assert h.send_chat("thinking...") is None              # chatting mid-round
    tj, rj = in_thread(lambda: j.play(S))
    assert j.send_chat("me too") is None
    th.join(5); tj.join(5)
    assert (rh, rj) == ([S], [R])
    assert wait_until(lambda: h.chat_unread() == 1 and j.chat_unread() == 1)


def test_twenty_rounds_with_chat_traffic_never_disturb_the_game(make):
    from rps_game.engine import Round, judge
    h, j, _ = make()
    for n in range(20):
        t1, r1 = in_thread(lambda: h.play(R)); t2, r2 = in_thread(lambda: j.play(P))
        h.send_chat(f"h{n}"); j.send_chat(f"j{n}")
        t1.join(5); t2.join(5)
        assert (r1, r2) == ([P], [R])
        h.record(Round(R, P, judge(R, P))); j.record(Round(P, R, judge(P, R)))
        time.sleep(0.05)                                    # stay under the sending limit
    assert h.state == j.state


# ============================================================ off, muted, limited

def test_chat_turned_off_neither_sends_nor_shows(make):
    h, j, _ = make(host_opts=dict(chat_enabled=False))
    assert h.send_chat("hello") == "Chat is turned off."
    assert j.send_chat("psst") is None
    time.sleep(0.15)
    assert h.chat_lines() == [] and h.chat_unread() == 0     # ignored, not stored


def test_muting_hides_incoming_messages_and_can_be_undone(make):
    h, j, _ = make()
    j.set_chat_muted(True)
    h.send_chat("while muted")
    time.sleep(0.15)
    assert j.chat_lines() == [] and j.chat_unread() == 0 and j.chat_muted
    assert j.send_chat("I can still talk") is None            # muting only hides what they say
    j.set_chat_muted(False)
    h.send_chat("after unmuting")
    assert wait_until(lambda: j.chat_unread() == 1)
    assert [l.text for l in j.chat_lines() if l.sender == "them"] == ["after unmuting"]


def test_sending_is_rate_limited_with_a_friendly_message(make):
    h, j, _ = make()
    results = [h.send_chat(f"m{i}") for i in range(chatmod.SEND_BURST + 2)]
    assert results[:chatmod.SEND_BURST] == [None] * chatmod.SEND_BURST
    assert all("too quickly" in r for r in results[chatmod.SEND_BURST:])


def test_a_flooding_opponent_is_dropped_then_muted_without_ending_the_game(make):
    h, j, _ = make(wrap=("join",))                           # host is a hand-driven flooder
    total = chatmod.RECV_BURST + chatmod.FLOOD_DROPS_BEFORE_MUTE + 5
    for i in range(total):
        send(h, proto.Chat(f"spam {i}"))
    assert wait_until(lambda: j.chat_muted)
    lines = j.chat_lines()
    assert sum(l.sender == "them" for l in lines) == chatmod.RECV_BURST    # the rest were dropped
    assert any(l.sender == "note" and "muted" in l.text for l in lines)
    assert j.error is None                                    # flooding is not a protocol violation
    assert j.crash is None


def test_an_invalid_message_from_the_peer_ends_the_game(make):
    h, j, _ = make(wrap=("join",))
    h.transport.send(b'{"t":"chat","text":"a\\u001bb"}')      # an escape character
    assert wait_until(lambda: j.error is not None)
    assert isinstance(j.error, ProtocolError)


def test_history_is_capped(make):
    from rps_game.net.game import CHAT_HISTORY
    h, j, _ = make(host_opts=dict(), join_opts=dict())
    for i in range(CHAT_HISTORY + 20):
        h._add_chat("me", f"m{i}")
    assert len(h.chat_lines(10_000)) == CHAT_HISTORY


def test_chat_survives_a_rematch_within_the_connection(make):
    h, j, _ = make()
    h.send_chat("before")
    t1, _ = in_thread(h.rematch); t2, _ = in_thread(j.rematch)
    t1.join(5); t2.join(5)
    h.send_chat("after")
    assert wait_until(lambda: [l.text for l in j.chat_lines()] == ["before", "after"])


# ============================================================ a chatty opponent isn't "gone"

def test_a_chat_message_extends_the_wait_for_a_slow_opponent(make):
    h, j, _ = make(wrap=("join",), commit_timeout=0.4)

    def chatter():                                             # present, but not committing
        for i in range(5):
            time.sleep(0.2)
            send(h, proto.Chat(f"brb {i}"))

    threading.Thread(target=chatter, daemon=True).start()
    started = time.monotonic()
    with pytest.raises(Timeout):
        j.play(R)
    waited = time.monotonic() - started
    assert 0.9 < waited <= 1.6, waited                         # > 0.4 (extended), <= 3 x 0.4 (cap) + slack


def test_without_chat_the_normal_limit_applies(make):
    h, j, _ = make(wrap=("join",), commit_timeout=0.4)
    started = time.monotonic()
    with pytest.raises(Timeout):
        j.play(R)
    assert time.monotonic() - started < 0.8


def test_endless_chatter_cannot_stall_forever(make):
    h, j, _ = make(wrap=("join",), commit_timeout=0.3)
    quit_chatter = threading.Event()

    def spam():
        while not quit_chatter.is_set():
            time.sleep(0.1)
            try:
                send(h, proto.Chat("still here"))
            except Exception:                                  # noqa: BLE001
                return

    threading.Thread(target=spam, daemon=True).start()
    started = time.monotonic()
    with pytest.raises(Timeout):
        j.play(R)
    quit_chatter.set()
    assert time.monotonic() - started < 1.6                    # capped at 3 x 0.3 = 0.9 s (+ slack)
