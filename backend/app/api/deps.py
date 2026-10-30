from typing import Annotated

from fastapi import Depends, Request

from app.config import Settings
from app.extract.service import Extractor
from app.find.service import Finder
from app.inventory.service import Inventory
from app.listing.service import Lister
from app.listing.voice import VoiceNotes
from app.match.service import Assessor
from app.measure.service import Measurer
from app.model_api import CostLedger, ModelApiClient
from app.ops.gate import Gate
from app.profiles import Profiles
from app.segment.service import Segmenter
from app.value.service import Valuer


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


def app_assessor(request: Request) -> Assessor:
    assessor: Assessor = request.app.state.assessor
    return assessor


AssessorDep = Annotated[Assessor, Depends(app_assessor)]


def app_lister(request: Request) -> Lister:
    lister: Lister = request.app.state.lister
    return lister


ListerDep = Annotated[Lister, Depends(app_lister)]


def app_voice(request: Request) -> VoiceNotes:
    voice: VoiceNotes = request.app.state.voice
    return voice


VoiceDep = Annotated[VoiceNotes, Depends(app_voice)]


def app_valuer(request: Request) -> Valuer:
    valuer: Valuer = request.app.state.valuer
    return valuer


ValuerDep = Annotated[Valuer, Depends(app_valuer)]


def app_finder(request: Request) -> Finder:
    finder: Finder = request.app.state.finder
    return finder


FinderDep = Annotated[Finder, Depends(app_finder)]


def app_gate(request: Request) -> Gate:
    gate: Gate = request.app.state.gate
    return gate


GateDep = Annotated[Gate, Depends(app_gate)]
