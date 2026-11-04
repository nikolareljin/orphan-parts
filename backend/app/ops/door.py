"""Which door a request came through. ``live_request`` is True for a request made with the
access code (or on a machine with no gate at all) and False for the demo visitor; the gate
sets it per request and the model client reads it to choose between the key and the recorded
answers. Outside a request it is True, so commands and tests behave as the owner."""

from contextvars import ContextVar
from typing import Protocol

live_request: ContextVar[bool] = ContextVar("live_request", default=True)

# A judge's code (app.keys scopes): its record's id while one of its requests is served, else 0.
# What the request makes is tagged with it, and what another code made is not there for it.
judge_code: ContextVar[int] = ContextVar("judge_code", default=0)
# a code kept on the recorded answers: the model client answers it from the fixture twin, as it
# answers the demo visitor, whatever door the request came through
recorded_request: ContextVar[bool] = ContextVar("recorded_request", default=False)
# set for every request the API serves to a person: in fixture mode such a request is answered
# by the recording of that exact request or refused, never by an operation's stand-in
# (FIXTURE_STUBS=1 lets the stand-ins answer, for the tests and the screenshot stacks)
served_request: ContextVar[bool] = ContextVar("served_request", default=False)


class Meter(Protocol):
    """The limits of the issued code a request is from: ``check`` before a call that bills
    (raises when the code may not make it, and holds the call while it is under way),
    ``charge`` after, with what it cost, or ``release`` when it failed unbilled."""

    def check(self) -> None: ...

    def charge(self, usd: float) -> None: ...

    def release(self) -> None: ...


code_meter: ContextVar[Meter | None] = ContextVar("code_meter", default=None)

# What the owner keeps to themselves on a record the demo visitor may read: where an item is,
# its notes and the voice notes said about it, a capture's line, clip and spoken note. The
# shapes blank these whenever they are serialized for the demo visitor, so every route that
# answers the visitor (and any added later) leaves them out without remembering to.
PRIVATE_SOURCES = frozenset({"voice_note"})
# The fields that are the owner's own words, kept like the notes: the device a part came from,
# as the owner described it (app.inventory.parent).
PRIVATE_FIELDS = frozenset({"parent_device"})


def for_visitor() -> bool:
    """Whether what is being answered goes to the demo visitor."""
    return not live_request.get()


def sandbox() -> int:
    """The judge's code this request is from, or 0 for the owner, a command or the visitor."""
    return judge_code.get()


def owned_sql(column: str, public: str | None = None) -> tuple[str, tuple[int, ...]]:
    """A SQL condition on a record's ``owner_code`` column for who is asking: the owner (and a
    command) sees every record; a judge the owner's and its own, with ``public`` (the column
    that marks a record for the public demo) required of the owner's; the demo visitor the
    owner's alone, never a judge's."""
    judge = judge_code.get()
    if judge:
        shown = f"{column} IS NULL" + (f" AND {public} = 1" if public else "")
        return f"(({shown}) OR {column} = ?)", (judge,)
    if not live_request.get():
        return f"{column} IS NULL", ()
    return "1 = 1", ()
