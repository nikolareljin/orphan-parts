"""The shared upload read: at most the cap, whatever the client declared."""

from io import BytesIO

import pytest
from fastapi import HTTPException, UploadFile

from app.api.uploads import read_bounded

pytestmark = pytest.mark.anyio

LINE = "a photo is larger than 1 MB"


def upload(body: bytes, size: int | None) -> UploadFile:
    return UploadFile(BytesIO(body), size=size)


async def test_a_small_part_passes_through() -> None:
    assert await read_bounded(upload(b"x" * 10, 10), 1024, LINE) == b"x" * 10


async def test_a_part_exactly_at_the_cap_passes() -> None:
    assert await read_bounded(upload(b"x" * 16, 16), 16, LINE) == b"x" * 16


async def test_a_part_past_the_cap_is_refused() -> None:
    with pytest.raises(HTTPException) as caught:
        await read_bounded(upload(b"x" * 17, 17), 16, LINE)
    assert caught.value.status_code == 400
    assert caught.value.detail == LINE


async def test_a_lying_declared_size_is_refused() -> None:
    with pytest.raises(HTTPException) as caught:
        await read_bounded(upload(b"x" * 1024, 10), 16, LINE)
    assert caught.value.status_code == 400


async def test_an_unknown_size_is_still_bounded() -> None:
    with pytest.raises(HTTPException) as caught:
        await read_bounded(upload(b"x" * 1024, None), 16, LINE)
    assert caught.value.status_code == 400


async def test_an_empty_part_passes_for_the_route_to_judge() -> None:
    assert await read_bounded(upload(b"", 0), 16, LINE) == b""
