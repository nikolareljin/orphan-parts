from typing import Annotated

from fastapi import Depends, Request

from app.config import Settings
from app.extract.service import Extractor
from app.model_api import CostLedger, ModelApiClient
from app.segment.service import Segmenter


def app_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def app_ledger(request: Request) -> CostLedger:
    ledger: CostLedger = request.app.state.ledger
    return ledger


def app_model_api(request: Request) -> ModelApiClient:
    client: ModelApiClient = request.app.state.model_api
    return client


def app_extractor(request: Request) -> Extractor:
    extractor: Extractor = request.app.state.extractor
    return extractor


def app_segmenter(request: Request) -> Segmenter:
    segmenter: Segmenter = request.app.state.segmenter
    return segmenter


SettingsDep = Annotated[Settings, Depends(app_settings)]
LedgerDep = Annotated[CostLedger, Depends(app_ledger)]
ModelApiDep = Annotated[ModelApiClient, Depends(app_model_api)]
ExtractorDep = Annotated[Extractor, Depends(app_extractor)]
SegmenterDep = Annotated[Segmenter, Depends(app_segmenter)]
