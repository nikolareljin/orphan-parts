"""Images the demo visitor's browser keeps and asks again for every time it shows them: the
tag is the bytes' own, so a number reused after a reset or a photo whose hidden areas changed
is a new tag, and an unchanged image costs a 304 with no body. The visitor sees public items
only, and the route's own lookup runs before any 304. Whatever the owner or a judge's code is
shown (a private item's drawing, a shared copy of a private photo) stays out of the browser's
cache, as before."""

import hashlib

from fastapi import Request
from fastapi.responses import Response

from app.ops.door import for_visitor


def revalidated_jpeg(request: Request, data: bytes) -> Response:
    if not for_visitor():
        return Response(data, media_type="image/jpeg", headers={"Cache-Control": "no-store"})
    tag = f'"{hashlib.sha256(data).hexdigest()[:32]}"'
    headers = {"Cache-Control": "private, no-cache", "ETag": tag}
    asked = {
        t.strip().removeprefix("W/") for t in request.headers.get("if-none-match", "").split(",")
    }
    if tag in asked:
        return Response(status_code=304, headers=headers)
    return Response(data, media_type="image/jpeg", headers=headers)
