"""Which door a request came through. ``live_request`` is True for a request made with the
access code (or on a machine with no gate at all) and False for the demo visitor; the gate
sets it per request and the model client reads it to choose between the key and the recorded
answers. Outside a request it is True, so commands and tests behave as the owner."""

from contextvars import ContextVar

live_request: ContextVar[bool] = ContextVar("live_request", default=True)

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
