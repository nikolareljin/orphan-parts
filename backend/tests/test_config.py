import pytest

from app.config import Settings


def test_missing_key_fails_fast_in_live_mode() -> None:
    with pytest.raises(ValueError, match="MODEL_API_KEY"):
        Settings(OPL_FAKE_API=False, model_api_key=None, _env_file=None)


def test_fixture_mode_needs_no_key() -> None:
    s = Settings(OPL_FAKE_API=True, _env_file=None)
    assert s.model_api_mode == "fixture"


def test_key_is_never_shown_in_repr() -> None:
    s = Settings(OPL_FAKE_API=False, model_api_key="not-a-real-key-123", _env_file=None)
    assert "not-a-real-key-123" not in repr(s)
    assert s.model_api_mode == "live"


def test_cors_origins_split_and_trimmed() -> None:
    s = Settings(OPL_FAKE_API=True, cors_origins="http://a, http://b ,", _env_file=None)
    assert s.cors_origin_list == ["http://a", "http://b"]


def test_price_settings_are_checked() -> None:
    with pytest.raises(ValueError, match="PRICE_COUNTRY"):
        Settings(OPL_FAKE_API=True, price_country="usa", _env_file=None)
    with pytest.raises(ValueError):
        Settings(OPL_FAKE_API=True, price_search_context="huge", _env_file=None)
    s = Settings(OPL_FAKE_API=True, price_country="US", price_search_context="high", _env_file=None)
    assert (s.price_country, s.price_search_context) == ("US", "high")
    with pytest.raises(ValueError, match="CANDIDATE_DAYS"):
        Settings(OPL_FAKE_API=True, candidate_days=0, _env_file=None)
