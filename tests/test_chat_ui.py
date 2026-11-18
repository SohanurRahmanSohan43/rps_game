"""Chat on the screens: the keys, the preview line, mute, plain-mode commands."""
import io
import threading
import time

from rich.console import Console

from netutil import connected_pair
from rps_game import cli, settings, terminal
from rps_game.dualsetup import DualSetup
from rps_game.engine import Match, Move, Round, Score, judge
from rps_game.net.errors import NetError
from rps_game.net.game import ChatLine, NetworkOpponent
from rps_game.net.play import play_dual
from rps_game.net.session import GameTerms
from rps_game.passkey import Passkey
from rps_game.players import Side
from rps_game.ui import GameUI, Option

ENTER, ESC, DOWN = terminal.KEY_ENTER, terminal.KEY_ESC, terminal.KEY_DOWN
R, P, S = Move.ROCK, Move.PAPER, Move.SCISSORS
SLOW = dict(ping_interval=60, first_ping_delay=60, liveness_timeout=600)
OPTIONS = [Option("Play again", "again"), Option("Back to the menu", "menu")]


class FakeChat:
    """Just enough of NetworkOpponent's chat API for screen tests."""

    def __init__(self, enabled=True):
        self.name = "Bob"
        self.chat_enabled = enabled
        self.sent, self.lines, self.unread = [], [], 0
        self.muted, self.error, self.refuse = False, None, None

    def send_chat(self, text):
        if self.refuse:
            return self.refuse
        self.sent.append(text)
        self.lines.append(ChatLine("me", text))
        return None

    def incoming(self, text):
        self.lines.append(ChatLine("them", text))
        self.unread += 1

    def chat_lines(self, limit=50):
        return self.lines[-limit:]

    def chat_unread(self):
        return self.unread

    def chat_mark_read(self):
        self.unread = 0

    def chat_take_unread(self):
        theirs = [l for l in self.lines if l.sender == "them"]
        n, self.unread = self.unread, 0
        return theirs[-n:] if n else []

    @property
    def chat_muted(self):
        return self.muted

    def set_chat_muted(self, value):
        self.muted = value

    def chat_preview(self):
        return next((l.text for l in reversed(self.lines) if l.sender == "them"), "")


def fake_terminal(monkeypatch, keys, polled=()):
    """Blocking-ish reads pop ``keys``; non-blocking polls (timeout=0) pop ``polled``."""
    pending, polls = list(keys), list(polled)

    def read_key(timeout=None):
        if timeout == 0:
            return polls.pop(0) if polls else None
        if not pending:
            raise AssertionError("the test ran out of keys")
        return pending.pop(0)

    monkeypatch.setattr(terminal, "is_interactive", lambda: True)
    monkeypatch.setattr(terminal, "flush_input", lambda: None)
    monkeypatch.setattr(terminal, "read_key", read_key)
    return pending


def round_screen(monkeypatch, keys, chat=None, polled=(), width=100, height=30):
    out = io.StringIO()
    ui = GameUI(animate=False, console=Console(file=out, width=width, height=height,
                                               force_terminal=False))
    fake_terminal(monkeypatch, keys, polled)
    if chat is not None:
        ui.set_chat(chat)
    ui.start_round(Match(), Score(), "")
    return ui, out


def spy(ui, name):
    """Record the arguments a UI method is called with."""
    calls, real = [], getattr(ui, name)

    def wrapper(*a, **kw):
        calls.append((a, kw))
        return real(*a, **kw)

    setattr(ui, name, wrapper)
    return calls


def ask(ui):
    return ui.ask_move(idle=lambda: "Bob is choosing...", leave_prompt="Leave the game?")


# ================================================================== the keys

def test_slash_opens_chat_enter_sends_slash_again_returns_to_the_move_prompt(monkeypatch):
    chat = FakeChat()
    ui, _ = round_screen(monkeypatch, ["/", "h", "i", ENTER, "/", "r"], chat)
    assert ask(ui) is R
    assert chat.sent == ["hi"]


def test_you_stay_in_chat_for_the_next_message(monkeypatch):
    chat = FakeChat()
    ui, _ = round_screen(monkeypatch, ["/", "a", ENTER, "b", ENTER, "c", ENTER, "/", "s"], chat)
    assert ask(ui) is S
    assert chat.sent == ["a", "b", "c"]


def test_a_slash_inside_a_message_is_just_a_slash(monkeypatch):
    chat = FakeChat()
    ui, _ = round_screen(monkeypatch, ["/", "1", "/", "2", ENTER, "/", "p"], chat)
    assert ask(ui) is P
    assert chat.sent == ["1/2"]


def test_a_url_with_slashes_survives(monkeypatch):
    chat = FakeChat()
    ui, _ = round_screen(monkeypatch, ["/", *"a.com/x/y", ENTER, "/", "r"], chat)
    ask(ui)
    assert chat.sent == ["a.com/x/y"]


def test_escape_leaves_chat_and_discards_the_unsent_text(monkeypatch):
    chat = FakeChat()
    ui, _ = round_screen(monkeypatch, ["/", "h", "e", ESC, "r"], chat)
    assert ask(ui) is R
    assert chat.sent == []


def test_game_keys_do_nothing_while_typing(monkeypatch):
    """Typing "rps" must not throw a move, and "q" must not trigger the leave prompt."""
    chat = FakeChat()
    ui, _ = round_screen(monkeypatch, ["/", "r", "p", "s", ENTER, "q", ENTER, "/", "s"], chat)
    assert ask(ui) is S                                        # only the final real keypress counted
    assert chat.sent == ["rps", "q"]


def test_an_empty_line_is_not_sent(monkeypatch):
    chat = FakeChat()
    ui, _ = round_screen(monkeypatch, ["/", ENTER, " ", " ", ENTER, "/", "r"], chat)
    ask(ui)
    assert chat.sent == []


def test_backspace_and_ctrl_u_edit_the_line(monkeypatch):
    chat = FakeChat()
    keys = ["/", "h", "x", terminal.KEY_BACKSPACE, "i", ENTER,
            "j", "u", "n", "k", "\x15", "o", "k", ENTER, "/", "r"]
    ui, _ = round_screen(monkeypatch, keys, chat)
    ask(ui)
    assert chat.sent == ["hi", "ok"]


def test_the_two_hundred_character_limit_is_enforced_while_typing(monkeypatch):
    chat = FakeChat()
    ui, _ = round_screen(monkeypatch, ["/", *("x" * 205), ENTER, "/", "r"], chat)
    notices = []
    real = ui._chat_view
    ui._chat_view = lambda text, notice: notices.append(notice) or real(text, notice)
    ask(ui)
    assert chat.sent == ["x" * 200]
    assert any("maximum length (200)" in n for n in notices)


def test_a_refused_message_shows_the_reason_and_stays_in_the_box(monkeypatch):
    chat = FakeChat()
    chat.refuse = "You're sending messages too quickly. Wait a moment."
    # the refused text stays in the box, so a "/" would now be a literal slash: leave with Esc
    ui, _ = round_screen(monkeypatch, ["/", "h", "i", ENTER, ESC, "r"], chat)
    notices = []
    real = ui._chat_view
    ui._chat_view = lambda text, notice: notices.append((text, notice)) or real(text, notice)
    ask(ui)
    assert ("hi", "You're sending messages too quickly. Wait a moment.") in notices


def test_non_ascii_text_can_be_typed(monkeypatch):
    chat = FakeChat()
    ui, _ = round_screen(monkeypatch, ["/", *"সোহান 😀", ENTER, "/", "r"], chat)
    ask(ui)
    assert chat.sent == ["সোহান 😀"]


def test_the_game_state_is_not_lost_after_chatting(monkeypatch):
    chat = FakeChat()
    ui, out = round_screen(monkeypatch, ["/", "h", ENTER, "/", "r"], chat)
    ask(ui)
    assert ui._live is not None                                # the round screen was put back
    ui.end_round()
    assert "Choose:" in out.getvalue() and "[/] chat" in out.getvalue()


# ================================================================== preview, unread, mute

def test_the_round_screen_shows_the_newest_message_and_how_many_are_new(monkeypatch):
    chat = FakeChat()
    chat.incoming("good luck!")
    chat.incoming("have fun")
    ui, _ = round_screen(monkeypatch, ["r"], chat)
    previews = spy(ui, "_draw")
    ask(ui)
    texts = [kw["chat"].plain for _, kw in previews if kw.get("chat") is not None]
    assert any("Bob: have fun  (2 new)" in t for t in texts)


def test_opening_chat_marks_messages_read(monkeypatch):
    chat = FakeChat()
    chat.incoming("psst")
    ui, _ = round_screen(monkeypatch, ["/", "/", "r"], chat)
    ask(ui)
    assert chat.unread == 0


def test_a_message_arriving_while_choosing_shows_up_without_a_keypress(monkeypatch):
    chat = FakeChat()
    ui, _ = round_screen(monkeypatch, ["r"], chat)
    drawn = spy(ui, "_draw")
    status_calls = []

    def idle():
        status_calls.append(1)
        if len(status_calls) == 2:
            chat.incoming("you there?")
        return "Bob is choosing..."

    keys_iter = iter([None, None, "r"])
    monkeypatch.setattr(terminal, "read_key", lambda timeout=None: next(keys_iter))
    assert ui.ask_move(idle=idle, leave_prompt="Leave?") is R
    assert any(kw.get("chat") is not None and "you there?" in kw["chat"].plain for _, kw in drawn)


def test_m_mutes_and_unmutes_the_opponents_messages(monkeypatch):
    chat = FakeChat()
    ui, _ = round_screen(monkeypatch, ["m", "m", "m", "r"], chat)
    states = []
    real = ui._toggle_mute
    ui._toggle_mute = lambda: (real(), states.append(chat.muted))
    ask(ui)
    assert states == [True, False, True] and chat.muted


def test_the_muted_preview_says_so(monkeypatch):
    chat = FakeChat()
    chat.muted = True
    ui, _ = round_screen(monkeypatch, ["r"], chat)
    assert "muted" in ui._chat_text().plain


def test_a_long_message_is_cut_to_fit_the_preview_line(monkeypatch):
    chat = FakeChat()
    chat.incoming("word " * 40)
    ui, _ = round_screen(monkeypatch, ["r"], chat, width=80)
    line = ui._chat_text().plain
    assert len(line) <= 80 and "\u2026" in line and "(1 new)" in line


def test_the_opponent_leaving_is_visible_in_the_chat_screen(monkeypatch):
    chat = FakeChat()
    chat.error = NetError("gone")
    ui, out = round_screen(monkeypatch, ["/", "/", "r"], chat)
    ask(ui)
    assert "Bob has left the game." in out.getvalue()


# ================================================================== chat on/off

def test_without_chat_the_slash_key_is_just_an_unknown_key(monkeypatch):
    ui, out = round_screen(monkeypatch, ["/", "r"], chat=None)
    assert ask(ui) is R
    assert ui._view.chat is None and "[/] chat" not in out.getvalue()


def test_a_disabled_chat_adds_no_chat_line_and_ignores_slash(monkeypatch):
    ui, out = round_screen(monkeypatch, ["/", "r"], FakeChat(enabled=False))
    assert ask(ui) is R and ui._view.chat is None


def test_single_player_screens_are_unchanged(monkeypatch):
    ui, out = round_screen(monkeypatch, [], chat=None)
    ui.end_round()
    assert "chat" not in out.getvalue().lower()


# ================================================================== waiting and results screens

def test_slash_opens_chat_while_waiting_for_the_opponent(monkeypatch):
    chat = FakeChat()
    keys = ["h", "i", ENTER, "/"]                              # typed inside chat
    ui, _ = round_screen(monkeypatch, keys, chat, polled=["/"])
    assert ui.opponent_wait("Waiting for Bob to lock in...", "Leave?") is True
    assert chat.sent == ["hi"]
    assert ui._live is not None                                # back on the round screen


def test_m_mutes_while_waiting(monkeypatch):
    chat = FakeChat()
    ui, _ = round_screen(monkeypatch, [], chat, polled=["m"])
    ui.opponent_wait("Waiting...", "Leave?")
    assert chat.muted


def test_q_still_offers_to_leave_while_waiting(monkeypatch):
    chat = FakeChat()
    ui, _ = round_screen(monkeypatch, ["y"], chat, polled=["q"])
    assert ui.opponent_wait("Waiting...", "Leave?") is False


def test_chat_works_from_the_results_menu(monkeypatch):
    chat = FakeChat()
    out = io.StringIO()
    ui = GameUI(animate=False, console=Console(file=out, width=100, height=30, force_terminal=False))
    ui.set_chat(chat)
    fake_terminal(monkeypatch, ["/", "g", "g", ENTER, "/", ENTER])    # chat "gg", back, pick the first option
    m = Match(first_to=1)
    m.play(R, S)
    choice = ui.results_menu("Game over", m.score, m, OPTIONS)
    assert choice == "again" and chat.sent == ["gg"]
    assert "/ chat" in out.getvalue()


def test_the_results_menu_shows_the_opponents_latest_message(monkeypatch):
    chat = FakeChat()
    chat.incoming("rematch?")
    out = io.StringIO()
    ui = GameUI(animate=False, console=Console(file=out, width=100, height=30, force_terminal=False))
    ui.set_chat(chat)
    fake_terminal(monkeypatch, [ENTER])
    m = Match(first_to=1)
    m.play(R, S)
    ui.results_menu("Game over", m.score, m, OPTIONS, idle=lambda: "Bob wants to play again.")
    text = out.getvalue()
    assert "Bob wants to play again." in text and "Bob: rematch?" in text


# ================================================================== plain (screen reader) mode

def plain_ui(chat):
    ui = GameUI(plain=True)
    ui.set_chat(chat)
    return ui


def feed(monkeypatch, lines):
    it = iter(lines)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(it))


def test_plain_slash_message_sends_and_the_move_prompt_returns(monkeypatch, capsys):
    chat = FakeChat()
    feed(monkeypatch, ["/hello there", "r"])
    assert plain_ui(chat).ask_move() is R
    assert chat.sent == ["hello there"]


def test_plain_message_keeps_its_capitals(monkeypatch):
    chat = FakeChat()
    feed(monkeypatch, ["/Good Game, Bob!", "r"])
    plain_ui(chat).ask_move()
    assert chat.sent == ["Good Game, Bob!"]


def test_plain_bare_slash_shows_recent_messages(monkeypatch, capsys):
    chat = FakeChat()
    chat.incoming("hi")
    chat.lines.append(ChatLine("me", "hello"))
    feed(monkeypatch, ["/", "r"])
    plain_ui(chat).ask_move()
    out = capsys.readouterr().out
    assert "Bob: hi" in out and "You: hello" in out


def test_plain_with_no_messages_says_how_to_start(monkeypatch, capsys):
    feed(monkeypatch, ["/", "r"])
    plain_ui(FakeChat()).ask_move()
    assert "Type /message to send one" in capsys.readouterr().out


def test_plain_new_messages_print_before_the_next_prompt(monkeypatch, capsys):
    chat = FakeChat()
    chat.incoming("yo")
    feed(monkeypatch, ["r"])
    plain_ui(chat).ask_move()
    assert "Bob: yo" in capsys.readouterr().out
    assert chat.unread == 0


def test_plain_mute_and_unmute(monkeypatch, capsys):
    chat = FakeChat()
    feed(monkeypatch, ["/mute", "/unmute", "/mute", "r"])
    plain_ui(chat).ask_move()
    assert chat.muted
    out = capsys.readouterr().out
    assert out.count("Chat muted.") == 2 and out.count("Chat unmuted.") == 1


def test_plain_refusals_are_read_out(monkeypatch, capsys):
    chat = FakeChat()
    chat.refuse = "You're sending messages too quickly. Wait a moment."
    feed(monkeypatch, ["/spam", "r"])
    plain_ui(chat).ask_move()
    assert "too quickly" in capsys.readouterr().out


def test_plain_chat_works_at_the_results_menu(monkeypatch):
    chat = FakeChat()
    feed(monkeypatch, ["/gg", "2"])
    m = Match(first_to=1)
    m.play(R, S)
    assert plain_ui(chat).results_menu("Game over", m.score, m, OPTIONS) == "menu"
    assert chat.sent == ["gg"]


def test_plain_chat_while_waiting_prints_arrivals(capsys):
    chat = FakeChat()
    ui = plain_ui(chat)
    ui.opponent_wait("Waiting for Bob to lock in...")
    chat.incoming("hang on")
    ui.opponent_wait("Waiting for Bob to lock in...")
    out = capsys.readouterr().out
    assert out.count("Waiting for Bob to lock in...") == 1 and "Bob: hang on" in out


def test_a_slash_command_is_ignored_when_chat_is_off(monkeypatch, capsys):
    feed(monkeypatch, ["/hello", "r"])
    ui = GameUI(plain=True)                                    # no chat attached: single player
    assert ui.ask_move() is R
    assert "not a valid move" in capsys.readouterr().out       # treated like any other bad input


def test_the_plain_intro_explains_chat_only_when_it_exists(capsys):
    ui = plain_ui(FakeChat())
    ui.intro(best_of=None, rounds=None, first_to=2, difficulty="")
    assert "/message to send" in capsys.readouterr().out
    ui2 = GameUI(plain=True)
    ui2.intro(best_of=None, rounds=None, first_to=2, difficulty="")
    assert "/message" not in capsys.readouterr().out


# ================================================================== whole games with real chat traffic

def host_setup(terms=GameTerms(first_to=2)):
    return DualSetup("host", "Sohan", Passkey("hunter22"), Side.LEFT, "482193756",
                     rounds=terms.rounds, first_to=terms.first_to)


def chatty_bot(seen, *, say=("hello",), moves=(S, S)):
    def run(opp):
        try:
            for text in say:
                opp.send_chat(text)
            for move in moves:
                theirs = opp.play(move)
                opp.record(Round(move, theirs, judge(move, theirs)))
            deadline = time.monotonic() + 3
            while opp.error is None and time.monotonic() < deadline:
                time.sleep(0.02)
        except NetError:
            pass
        finally:
            seen.extend(opp.chat_lines())
            opp.close()
    return run


def test_chat_and_play_together_in_plain_mode(monkeypatch, capsys):
    host, join, _ = connected_pair(terms=GameTerms(first_to=2))
    seen = []
    t = threading.Thread(target=lambda: chatty_bot(seen)(NetworkOpponent(join, **SLOW)), daemon=True)
    t.start()
    answers = iter(["/hi there", "r", "r", "2"])

    def typed(prompt=""):
        time.sleep(0.25)                                       # give "hello" time to arrive
        return next(answers)

    monkeypatch.setattr("builtins.input", typed)
    ui = GameUI(plain=True)
    play_dual(ui, host_setup(), host, run_game=cli.run_game, **SLOW)
    t.join(10)
    out = capsys.readouterr().out
    assert "Bob: hello" in out and "You won the match 2-0!" in out
    assert [l.text for l in seen if l.sender == "them"] == ["hi there"]
    assert ui._chat is None                                    # detached afterwards
    assert "Chat: type /message" in out


def test_chat_off_in_settings_means_no_chat_during_the_game(monkeypatch, capsys):
    settings.save(settings.Settings(chat_enabled=False))
    host, join, _ = connected_pair(terms=GameTerms(first_to=2))
    seen = []
    t = threading.Thread(target=lambda: chatty_bot(seen)(NetworkOpponent(join, **SLOW)), daemon=True)
    t.start()
    answers = iter(["/hi", "r", "r", "2"])
    monkeypatch.setattr("builtins.input", lambda prompt="": (time.sleep(0.2), next(answers))[1])
    ui = GameUI(plain=True)
    attached = []
    real = ui.set_chat
    ui.set_chat = lambda port: attached.append(port) or real(port)
    play_dual(ui, host_setup(), host, run_game=cli.run_game, **SLOW)
    t.join(10)
    out = capsys.readouterr().out
    assert attached[0] is None and "Bob: hello" not in out and "Chat: type" not in out
    assert "not a valid move" in out                           # "/hi" is just bad input without chat
    assert [l for l in seen if l.sender == "them"] == []


def test_chatting_for_a_long_time_never_costs_a_round(monkeypatch):
    """The reveal is automatic: sitting in the chat screen while the opponent reveals is safe."""
    host, join, _ = connected_pair(terms=GameTerms(first_to=1))
    seen = []

    def slow_bot(opp):
        try:
            time.sleep(0.5)                                    # commits only after the host is waiting
            theirs = opp.play(S)
            opp.record(Round(S, theirs, judge(S, theirs)))
            time.sleep(1.0)
        except NetError:
            pass
        finally:
            seen.extend(opp.chat_lines())
            opp.close()

    t = threading.Thread(target=lambda: slow_bot(NetworkOpponent(join, reveal_timeout=0.4, **SLOW)),
                         daemon=True)
    t.start()
    out = io.StringIO()
    ui = GameUI(animate=False, console=Console(file=out, width=100, height=30, force_terminal=False))
    # r (move), then while waiting "/" opens chat: type "brb", Enter, "/" back; then results: pick "menu"
    pending = ["r", *"brb", ENTER, "/", DOWN, ENTER]
    polls = [None, None, "/"]
    monkeypatch.setattr(terminal, "is_interactive", lambda: True)
    monkeypatch.setattr(terminal, "flush_input", lambda: None)

    def read_key(timeout=None):
        if timeout == 0:
            return polls.pop(0) if polls else None
        if not pending:
            return None
        if pending[0] == "/" and len(pending) > 1 and pending[1] == DOWN:
            pass
        return pending.pop(0)

    monkeypatch.setattr(terminal, "read_key", read_key)
    play_dual(ui, host_setup(GameTerms(first_to=1)), host, run_game=cli.run_game, **SLOW)
    t.join(10)
    text = out.getvalue()
    assert "YOU WIN!" in text
    assert "You win by forfeit" not in text                    # (the hint line mentions forfeiting)
    assert [l.text for l in seen if l.sender == "them"] == ["brb"]


def test_a_line_of_only_spaces_counts_as_empty_for_the_leave_slash(monkeypatch):
    chat = FakeChat()
    ui, _ = round_screen(monkeypatch, ["/", " ", " ", "/", "r"], chat)
    assert ask(ui) is R and chat.sent == []
