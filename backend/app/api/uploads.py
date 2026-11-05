"""One bounded read for upload parts, shared by every feature route."""

from fastapi import HTTPException, UploadFile


async def read_bounded(upload: UploadFile, cap: int, detail: str) -> bytes:
    """At most ``cap`` bytes of the part: one byte past the cap refuses it with ``detail``,
    whatever the client declared."""
    part = await upload.read(cap + 1)
    if len(part) > cap:
        raise HTTPException(status_code=400, detail=detail)
    return part
