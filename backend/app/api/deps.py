from typing import Annotated

from fastapi import Depends, Request

from app.config import Settings
from app.extract.service import Extractor
from app.inventory.service import Inventory
from app.measure.service import Measurer
from app.model_api import CostLedger, ModelApiClient
from app.profiles import Profiles
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


def app_inventory(request: Request) -> Inventory:
    inventory: Inventory = request.app.state.inventory
    return inventory


InventoryDep = Annotated[Inventory, Depends(app_inventory)]


def app_profiles(request: Request) -> Profiles:
    profiles: Profiles = request.app.state.profiles
    return profiles


def app_measurer(request: Request) -> Measurer:
    measurer: Measurer = request.app.state.measurer
    return measurer


ProfilesDep = Annotated[Profiles, Depends(app_profiles)]
MeasurerDep = Annotated[Measurer, Depends(app_measurer)]
