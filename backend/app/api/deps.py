from typing import Annotated

from fastapi import Depends, Request

from app.captures.service import Captures
from app.config import Settings
from app.decide.service import Decider
from app.extract.service import Extractor
from app.find.service import Finder
from app.inventory.service import Inventory
from app.listing.handoff import Handoff
from app.listing.service import Lister
from app.listing.voice import VoiceNotes
from app.match.service import Assessor
from app.measure.service import Measurer
from app.model_api import CostLedger, ModelApiClient
from app.ops.gate import Gate
from app.photos import ItemPhotos
from app.picture import Pictures
from app.profiles import Profiles
from app.projects.service import Planner
from app.samples import SampleReader, Samples
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


def app_handoff(request: Request) -> Handoff:
    handoff: Handoff = request.app.state.handoff
    return handoff


HandoffDep = Annotated[Handoff, Depends(app_handoff)]


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


def app_planner(request: Request) -> Planner:
    planner: Planner = request.app.state.planner
    return planner


PlannerDep = Annotated[Planner, Depends(app_planner)]


def app_captures(request: Request) -> Captures:
    captures: Captures = request.app.state.captures
    return captures


CapturesDep = Annotated[Captures, Depends(app_captures)]


def app_photos(request: Request) -> ItemPhotos:
    photos: ItemPhotos = request.app.state.photos
    return photos


PhotosDep = Annotated[ItemPhotos, Depends(app_photos)]


def app_pictures(request: Request) -> Pictures:
    pictures: Pictures = request.app.state.pictures
    return pictures


PicturesDep = Annotated[Pictures, Depends(app_pictures)]


def app_decider(request: Request) -> Decider:
    decider: Decider = request.app.state.decider
    return decider


DeciderDep = Annotated[Decider, Depends(app_decider)]


def app_samples(request: Request) -> Samples:
    samples: Samples = request.app.state.samples
    return samples


SamplesDep = Annotated[Samples, Depends(app_samples)]


def app_sample_reader(request: Request) -> SampleReader:
    reader: SampleReader = request.app.state.sample_reader
    return reader


SampleReaderDep = Annotated[SampleReader, Depends(app_sample_reader)]
