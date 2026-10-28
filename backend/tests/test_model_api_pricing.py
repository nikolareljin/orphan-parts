import logging

import pytest

from app.model_api.pricing import Usage, cost_usd, token_rates


def test_spark_tokens_are_priced_with_cached_discount() -> None:
    usage = Usage(input_tokens=1000, cached_tokens=200, output_tokens=500)
    # 800 uncached * 1.25 + 200 cached * 0.15 + 500 output * 4.25, per million
    assert cost_usd("muse-spark-1.3", usage) == pytest.approx(0.003155)


def test_wonder_costs_more_than_spark_for_the_same_usage() -> None:
    usage = Usage(input_tokens=1000, output_tokens=1000)
    assert cost_usd("muse-wonder-1.0", usage) > cost_usd("muse-spark-1.3", usage)


def test_contributor_models_use_contributor_rates() -> None:
    assert token_rates("muse-spark-1.3-contributor") == (0.002, 0.10, 0.20)


def test_unknown_model_is_charged_at_the_highest_rate(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="app.model_api.pricing"):
        rates = token_rates("muse-future-9.9")
    assert rates == token_rates("muse-wonder-1.0")
    assert "no price for model" in caplog.text


def test_sam_is_priced_per_image_and_per_frame_with_a_floor() -> None:
    assert cost_usd("sam-3.1", Usage(images=4)) == pytest.approx(0.01)
    # fewer than 50 frames still bills 50
    assert cost_usd("sam-3.1", Usage(video_frames=10)) == pytest.approx(0.01)
    assert cost_usd("sam-3.1", Usage(video_frames=100)) == pytest.approx(0.02)


def test_image_generation_bills_at_least_one_image() -> None:
    assert cost_usd("muse-image-1.0", Usage()) == pytest.approx(0.01)
    assert cost_usd("muse-image-1.0", Usage(images=3)) == pytest.approx(0.03)


def test_voice_is_priced_per_hour_of_audio() -> None:
    assert cost_usd("muse-voice-transcribe-1.0", Usage(audio_seconds=3600)) == pytest.approx(0.18)


def test_search_queries_add_to_token_cost() -> None:
    base = cost_usd("muse-spark-1.3", Usage(input_tokens=100))
    with_search = cost_usd("muse-spark-1.3", Usage(input_tokens=100, search_queries=2))
    assert with_search - base == pytest.approx(0.005)


def test_usage_reads_the_nested_response_fields() -> None:
    usage = Usage.from_response(
        {
            "input_tokens": 15,
            "input_tokens_details": {"cached_tokens": 5},
            "output_tokens": 258,
            "output_tokens_details": {"reasoning_tokens": 241},
            "total_tokens": 273,
        }
    )
    assert (usage.input_tokens, usage.cached_tokens) == (15, 5)
    assert (usage.output_tokens, usage.reasoning_tokens) == (258, 241)


def test_usage_tolerates_missing_or_odd_fields() -> None:
    assert Usage.from_response(None) == Usage()
    usage = Usage.from_response({"input_tokens": "12", "input_tokens_details": "x"})
    assert usage.input_tokens == 0
    assert usage.cached_tokens == 0
