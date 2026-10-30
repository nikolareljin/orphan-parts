"""Which door a request came through. ``live_request`` is True for a request made with the
access code (or on a machine with no gate at all) and False for the demo visitor; the gate
sets it per request and the model client reads it to choose between the key and the recorded
answers. Outside a request it is True, so commands and tests behave as the owner."""

from contextvars import ContextVar

live_request: ContextVar[bool] = ContextVar("live_request", default=True)
