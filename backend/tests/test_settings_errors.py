import pytest

from app.config import SettingsError, get_settings

# made up, built from parts so it never reads as a key
SECRET = "-".join(["fake", "key", "for", "tests", "x" * 12])


def test_a_refused_setting_never_shows_the_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MODEL_API_KEY", SECRET)
    monkeypatch.setenv("CANDIDATE_DAYS", "not a number")
    get_settings.cache_clear()
    try:
        with pytest.raises(SettingsError) as caught:
            get_settings()
    finally:
        get_settings.cache_clear()
    message = str(caught.value)
    assert "candidate_days" in message.lower()
    assert SECRET not in message
    assert SECRET[:6] not in message
    # nothing chained that a traceback would print with the input
    assert caught.value.__cause__ is None
    assert caught.value.__suppress_context__
