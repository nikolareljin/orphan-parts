from fastapi import APIRouter

from app.api.deps import ValuerDep
from app.api.model_errors import as_http
from app.value import Guidance, PriceReport, PriceReportCreate, PriceRequest

router = APIRouter(prefix="/api", tags=["value"])


@router.post("/items/{item_id}/price", response_model=Guidance, status_code=201)
async def price_item(item_id: int, request: PriceRequest, valuer: ValuerDep) -> Guidance:
    """Price guidance for an item. Muse Spark searches the web for listings and sales of the
    same model and condition; only comparables a search result backs are kept. Four quantities
    stay apart (asking, sold, what you reported, the model's estimate), each with its count,
    range, source and date; three labelled strategies; weak evidence is called weak. When the
    item has parts with guidance of their own, whole and parts are compared."""
    try:
        return await valuer.guide(item_id, request)
    except Exception as exc:
        raise as_http(exc) from exc


@router.get("/items/{item_id}/price", response_model=list[Guidance])
def price_history(item_id: int, valuer: ValuerDep) -> list[Guidance]:
    """Every guidance written for the item, newest last, each saying whether the item changed
    since."""
    return valuer.guidances(item_id)


@router.post("/items/{item_id}/price/reports", response_model=PriceReport, status_code=201)
def report_sale(item_id: int, spec: PriceReportCreate, valuer: ValuerDep) -> PriceReport:
    """A sale you know of: yours, or one you saw. Kept apart from everything the search finds,
    and counted under 'sales you reported' in the next guidance."""
    return valuer.report(item_id, spec)


@router.get("/items/{item_id}/price/reports", response_model=list[PriceReport])
def reported_sales(item_id: int, valuer: ValuerDep) -> list[PriceReport]:
    return valuer.reports(item_id)
