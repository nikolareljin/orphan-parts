"""The compatibility rules: the readers, each pairing (pass, fail, unknown), a project's
allocations refused in the tool loop and by the rules, a card's "with what you have" checked,
and an allocation swapped or taken off by hand."""

import json
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from fastapi.testclient import TestClient

from app.compat import Reading, Rules, card_check, check, set_pairings
from app.compat import normalize as norm
from app.config import Settings
from app.decide.service import Decider
from app.extract import Extractor
from app.find import Finder
from app.inventory import Inventory
from app.inventory.schema import FieldCreate, Item, ItemCreate, ItemPatch
from app.main import create_app
from app.match import Assessor
from app.model_api import CostLedger, ModelApiClient
from app.profiles import Profiles
from app.projects import FillRequest, Planner, ProjectsError, ProposeRequest, Templates
from app.projects.schema import visitor_markdown

pytestmark = pytest.mark.anyio


# --- the readers ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("PC3-12800S", "DDR3"),
        ("PC3L-12800S-11-13-B4", "DDR3L"),
        ("8GB 1Rx8 PC4-2666V-SA1-11", "DDR4"),
        ("PC2-6400", "DDR2"),
        ("DDR4-2666 SO-DIMM", "DDR4"),
        ("DDR3L 1600", "DDR3L"),
        ("ddr5", "DDR5"),
        ("SO-DIMM 260-pin", "DDR4"),
        ("204-pin SODIMM", "DDR3"),
        ("200 pin", "DDR2"),
        ("240-pin DIMM", None),
        ("LPDDR4X soldered", None),
        ("RMSA3270ME86H9F-2666", None),
        ("a stick of memory", None),
    ],
)
def test_memory_type_is_read_off_the_standard_the_label_prints(
    text: str, expected: str | None
) -> None:
    assert norm.memory_type(text) == expected


def test_memory_form_socket_board_and_drive_readers() -> None:
    assert norm.memory_form("SO-DIMM 260-pin") == "SO-DIMM"
    assert norm.memory_form("204-pin") == "SO-DIMM"
    assert norm.memory_form("288-pin") == "DIMM"
    assert norm.memory_form("UDIMM") == "DIMM" and norm.memory_form("unbuffered") is None
    assert norm.socket("LGA1155") == "LGA1155" and norm.socket("LGA 775") == "LGA775"
    assert norm.socket("Socket 1155") == "LGA1155" and norm.socket("Socket 370") == "Socket 370"
    assert norm.socket("socket AM4") == "AM4" and norm.socket("AM3+") == "AM3+"
    assert norm.socket("Intel slot 1 processor") == "Slot 1" and norm.socket("a CPU") is None
    assert norm.board_form("Micro-ATX") == "mATX" and norm.board_form("mini-ITX") == "ITX"
    assert norm.board_form("ATX board") == "ATX" and norm.board_form("E-ATX") == "E-ATX"
    assert norm.drive_size('2.5" SATA') == "2.5" and norm.drive_size("3.5 inch") == "3.5"
    assert norm.drive_size("2.5-inch") == "2.5" and norm.drive_size("12.5 inch") is None
    assert norm.interface("NVMe M.2") == "NVMe" and norm.interface("sata") == "SATA"
    assert norm.interface("mSATA") == "SATA" and norm.interface("IDE 44-pin") == "IDE"
    assert norm.drive_form("M.2 2280 NVMe") == "M.2" and norm.drive_form("2.5 inch SSD") == "2.5"
    assert norm.drive_form("M.2 and mSATA") is None  # two forms: not one drive's
    assert norm.buses("AGP 4x") == ["AGP"] and norm.buses("PCI-E x16") == ["PCIe"]
    assert norm.buses("PCI slot") == ["PCI"] and norm.logic_volts("5V") == "5"
    assert norm.buses("mini-PCIe Wi-Fi card") == [] and norm.buses("Mini PCIe") == []
    assert norm.socket("FCLGA1155") == "LGA1155"


@pytest.mark.parametrize(
    ("name", "holds", "plug"),
    [
        ("M.2 SSD to USB enclosure, open", ["M.2"], "USB"),
        ("M.2 and mSATA to SATA adapter", ["M.2", "mSATA"], "SATA"),
        ("M.2 to U.2 adapter", ["U.2"], "M.2"),
        ("PCIe adapter card for two M.2 drives", ["M.2"], "PCIe"),
        ("2.5 inch SATA to USB enclosure", ["2.5"], "USB"),
        ("2.5 to 3.5 inch drive bay adapter", ["2.5"], None),
        ('2.5" to 3.5" caddy', ["2.5"], None),
        ("M.2 to 2.5 inch SATA adapter", ["M.2"], "SATA"),
        ("enclosure", [], None),
    ],
)
def test_what_an_adapter_takes_and_plugs_into(
    name: str, holds: list[str], plug: str | None
) -> None:
    assert norm.holds(name) == holds and norm.plug(name) == plug


# --- an item read as the rules read it -------------------------------------------------------


def make(inv: Inventory, item_type: str, name: str, **fields: str) -> Item:
    item = inv.create(ItemCreate(item_type=item_type, name=name))
    for key, value in fields.items():
        inv.add_field(item.id, FieldCreate(field=key, value=value))
    return inv.get(item.id)


def test_items_are_read_from_their_values_the_known_parts_and_their_names(
    settings: Settings,
) -> None:
    inv, rules = Inventory(settings), Rules()
    hynix = rules.read(
        make(inv, "laptop memory", "SK hynix stick", part_number="HMAA1GS6CJR6N-XNNOBD")
    )
    assert hynix.role == "memory" and hynix.attrs == {
        "memory_type": "DDR4",
        "memory_form": "SO-DIMM",
    }
    t510 = rules.read(make(inv, "laptop", "Work laptop", model_number="TYPE4313-CTUS/"))
    assert t510.role == "laptop" and t510.get("memory_type") == "DDR3" and t510.get("bay") == "2.5"
    # a value the item states wins over the known part, and over its name
    stated = rules.read(make(inv, "desktop memory", "DDR4 stick", memory_type="PC3-12800"))
    assert stated.get("memory_type") == "DDR3" and stated.get("memory_form") == "DIMM"
    board = rules.read(make(inv, "motherboard", "Board", model_number="P8Z77-VLX"))
    assert board.get("socket") == "LGA1155" and "SATA" in board.get("slots")
    cpu = rules.read(make(inv, "processor", "Intel slot 1 processor with its fan"))
    assert cpu.role == "processor" and cpu.get("socket") == "Slot 1"
    # a powerline adapter is no drive adapter; a type nothing pairs has no role
    assert rules.role_of("powerline adapter") is None and rules.role_of("monitor") is None
    assert rules.role_of("microcontroller board") == "controller"
    assert rules.role_of("relay module") == "module" and rules.role_of("adapter card") == "adapter"
    # nothing known: no attribute is guessed
    assert rules.read(make(inv, "laptop", "Dell laptop")).attrs == {"memory_form": "SO-DIMM"}


def reading(role: str, name: str = "", **attrs: Any) -> Reading:
    reading.n = getattr(reading, "n", 0) + 1  # type: ignore[attr-defined]
    return Reading(reading.n, name or role, attrs.pop("item_type", role), role, attrs)  # type: ignore[attr-defined]


def test_memory_pairs_by_generation_and_form() -> None:
    laptop = reading("laptop", "T510", memory_type="DDR3", memory_form="SO-DIMM")
    ddr4 = reading("memory", "hynix", memory_type="DDR4", memory_form="SO-DIMM")
    ddr3l = reading("memory", "adata", memory_type="DDR3L", memory_form="SO-DIMM")
    dimm = reading("memory", "gskill", memory_type="DDR3", memory_form="DIMM")
    bare = reading("memory", "stick")
    found = check(ddr4, laptop)
    assert found is not None and found.state == "fail"
    assert found.reason == "DDR4 SO-DIMM in a DDR3 laptop"
    assert found.need_part == "DDR3 SO-DIMM laptop memory"
    ok = check(ddr3l, laptop)
    assert ok is not None and ok.state == "pass" and "1.5 V" in ok.reason
    form = check(dimm, laptop)
    assert form is not None and form.state == "fail" and "SO-DIMMs" in form.reason
    unknown = check(bare, laptop)
    assert unknown is not None and unknown.state == "unknown" and "not recorded" in unknown.reason
    # memory and a laptop pair; a monitor and memory do not
    assert check(ddr4, reading("monitor")) is None


def test_a_processor_pairs_by_socket() -> None:
    board = reading("board", "ASUS", socket="LGA1155")
    assert check(reading("processor", socket="LGA1155"), board).state == "pass"  # type: ignore[union-attr]
    slot1 = check(reading("processor", "Pentium", socket="Slot 1"), board)
    assert slot1 is not None and slot1.state == "fail"
    assert slot1.reason == "a Slot 1 processor does not fit an LGA1155 board"
    assert slot1.need_part == "LGA1155 processor"
    assert check(reading("processor"), board).state == "unknown"  # type: ignore[union-attr]


def test_a_drive_pairs_with_a_bay_a_port_and_an_adapter() -> None:
    laptop = reading("laptop", bay="2.5", interface="SATA")
    ssd = reading("drive", "A400", drive_form="2.5", interface="SATA")
    big = reading("drive", "Maxtor", drive_form="3.5", interface="SATA")
    m2 = reading("drive", "NVMe stick", drive_form="M.2", interface="NVMe")
    board = reading("board", slots=["PCIe", "SATA"])
    enclosure = reading("enclosure", "USB box", holds=["M.2"], item_type="enclosure")
    assert check(ssd, laptop).state == "pass"  # type: ignore[union-attr]
    assert check(big, laptop).state == "fail"  # type: ignore[union-attr]
    assert check(ssd, reading("laptop")).state == "unknown"  # type: ignore[union-attr]
    assert check(big, board).state == "pass"  # type: ignore[union-attr]
    assert check(m2, board).state == "fail"  # type: ignore[union-attr]
    assert check(m2, enclosure).state == "pass"  # type: ignore[union-attr]
    held = check(ssd, enclosure)
    assert held is not None and held.state == "fail" and held.need_part == "M.2 drive"


def test_cards_adapters_and_modules_pair_with_their_hosts() -> None:
    board = reading("board", slots=["PCIe", "SATA"])
    assert check(reading("card", bus="AGP"), board).state == "fail"  # type: ignore[union-attr]
    assert check(reading("card", bus="PCIe"), board).state == "pass"  # type: ignore[union-attr]
    assert check(reading("adapter", plug="M.2"), board).state == "fail"  # type: ignore[union-attr]
    assert check(reading("adapter", plug="USB"), board) is None
    box = reading("enclosure", "M.2 box", holds=["M.2"], item_type="enclosure")
    housed = check(reading("module", "Joystick"), box)
    assert housed is not None and housed.state == "fail" and housed.replace == "host"
    sized = reading("enclosure", "Tin", dims=[100.0, 60.0, 30.0])
    assert check(reading("module", dims=[20.0, 40.0, 10.0]), sized).state == "pass"  # type: ignore[union-attr]
    assert check(reading("module", dims=[120.0, 40.0, 10.0]), sized).state == "fail"  # type: ignore[union-attr]
    assert check(reading("module"), reading("enclosure")).state == "unknown"  # type: ignore[union-attr]
    uno = reading("controller", logic_volts="5")
    assert check(reading("module", logic_volts="5"), uno).state == "pass"  # type: ignore[union-attr]
    assert (
        check(reading("module", logic_volts="5"), reading("controller", logic_volts="3.3")).state
        == "fail"
    )  # type: ignore[union-attr]
    # nothing known of either side's level: no line rather than an unknown on every module
    assert check(reading("module"), uno) is None


def test_a_set_takes_each_part_s_best_host_and_names_the_missing_drive() -> None:
    board = reading("board", "ASRock", slots=["PCIe", "SATA", "M.2"])
    ssd = reading("drive", "A400", drive_form="2.5", interface="SATA")
    adapter = reading("adapter", "PCIe card", holds=["M.2"], plug="PCIe", item_type="adapter card")
    found = set_pairings([board, ssd, adapter], [])
    # the SSD is on the board's SATA port, not failed by the M.2 card beside it
    drive = next(p for p in found if p.part_id == ssd.id)
    assert drive.state == "pass" and drive.host_id == board.id
    missing = next(p for p in found if p.rule == "missing")
    assert missing.state == "fail" and missing.search == "M.2 drive"
    assert missing.fix == "needs an M.2 drive — not in your inventory; search it"
    # one of yours that fits is named instead of a search
    nvme = reading("drive", "NVMe stick", drive_form="M.2", interface="NVMe")
    found = set_pairings([board, ssd, adapter], [nvme])
    missing = next(p for p in found if p.rule == "missing")
    assert missing.fix == "use NVMe stick, it fits" and missing.search == ""


def test_a_card_keeps_only_what_works_with_its_item() -> None:
    board = reading(
        "board",
        "ASUS P8Z77",
        socket="LGA1155",
        memory_type="DDR3",
        memory_form="DIMM",
        item_type="motherboard",
    )
    cpu = reading("processor", "Slot 1 Pentium", socket="Slot 1", item_type="processor")
    card = reading("card", "9800 GT", bus="PCIe", item_type="graphics card")
    board.attrs["slots"] = ["PCIe", "SATA"]
    checked = card_check(board, ["processor", "graphics card", "monitor"], [board, cpu, card])
    assert checked.kept == ["graphics card", "monitor"] and checked.dropped == ["processor"]
    fail = next(p for p in checked.pairings if p.state == "fail")
    assert fail.fix == "needs an LGA1155 processor — not in your inventory; search it"
    assert fail.search == "LGA1155 processor"
    # the owned board that fits is chosen over one that does not
    ddr4 = reading(
        "memory", "Patriot", memory_type="DDR4", memory_form="DIMM", item_type="desktop memory"
    )
    am4 = reading(
        "board",
        "ASRock",
        socket="AM4",
        memory_type="DDR4",
        memory_form="DIMM",
        item_type="motherboard",
    )
    checked = card_check(ddr4, ["motherboard"], [board, am4, ddr4])
    assert [p.host for p in checked.pairings] == ["ASRock"] and checked.kept == ["motherboard"]
    # modules built into a drive enclosure: the box is what goes, said once
    uno = reading("controller", "UNO", item_type="microcontroller board")
    rtc = reading("module", "RTC", item_type="real-time clock module")
    box = reading("enclosure", "M.2 box", holds=["M.2"], item_type="enclosure")
    dht = reading("module", "DHT11", item_type="sensor module")
    checked = card_check(
        dht, ["microcontroller board", "real-time clock module", "enclosure"], [uno, rtc, box, dht]
    )
    assert checked.dropped == ["enclosure"] and len(checked.pairings) == 1
    assert (
        checked.pairings[0].part == "DHT11, UNO, RTC" and "project box" in checked.pairings[0].fix
    )


# --- projects ---------------------------------------------------------------------------------


def demo_drawer(inv: Inventory) -> dict[str, Item]:
    return {
        "t510": make(inv, "laptop", "ThinkPad T510", model_number="TYPE4313-CTUS/"),
        "hynix": make(inv, "laptop memory", "SK hynix 8 GB", part_number="HMAA1GS6CJR6N-XNNOBD"),
        "adata": make(inv, "laptop memory", "ADATA 8 GB", model_number="AM1L16BC8R2-B1QS"),
        "monitor": make(inv, "monitor", "Spare monitor"),
    }


def planner_for(settings: Settings, transport: httpx.MockTransport | None = None) -> Planner:
    client = ModelApiClient(settings, CostLedger(cap_usd=25.0), transport=transport)
    inventory = Inventory(settings)
    profiles = Profiles()
    finder = Finder(
        settings,
        client,
        inventory,
        profiles,
        Extractor(settings, client),
        Assessor(profiles, inventory),
    )
    return Planner(settings, client, inventory, Templates(), finder)


def answer(text: str, n: int) -> dict[str, Any]:
    return {
        "id": f"resp_{n}",
        "object": "response",
        "status": "completed",
        "model": "muse-spark-1.3",
        "output": [
            {
                "id": f"msg_{n}",
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "annotations": [], "text": text}],
            }
        ],
        "usage": {"input_tokens": 10, "output_tokens": 10, "total_tokens": 20},
    }


def call(name: str, args: dict[str, Any], n: int) -> dict[str, Any]:
    return {
        "id": f"resp_{n}",
        "object": "response",
        "status": "completed",
        "model": "muse-spark-1.3",
        "output": [
            {
                "id": f"fc_{n}",
                "type": "function_call",
                "status": "completed",
                "call_id": f"call_{n}",
                "name": name,
                "arguments": json.dumps(args),
            }
        ],
        "usage": {"input_tokens": 10, "output_tokens": 10, "total_tokens": 20},
    }


def proposal(server: int, memory: int) -> str:
    return json.dumps(
        {
            "proposals": [
                {
                    "template": "home_automation_server",
                    "title": "Home automation on the T510",
                    "result": "a laptop on a shelf running the house",
                    "allocations": [
                        {"requirement": "server", "item_id": server, "item_name": "", "why": "on"},
                        {
                            "requirement": "memory",
                            "item_id": memory,
                            "item_name": "",
                            "why": "more",
                        },
                    ],
                    "missing": [],
                    "effort": "medium",
                    "spend_estimate": 0,
                    "unknowns": [],
                }
            ]
        }
    )


async def test_the_tool_loop_refuses_an_incompatible_pick_and_the_model_picks_another(
    live_settings: Settings,
) -> None:
    settings = live_settings.model_copy(update={"compat_prompts": True})
    bodies: list[dict[str, Any]] = []
    items: dict[str, Item] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        bodies.append(body)
        picks = [
            {"requirement": "server", "item_id": items["t510"].id},
            {"requirement": "memory", "item_id": items["hynix"].id},
        ]
        if len(bodies) == 1:
            args = {"template": "home_automation_server", "picks": picks}
            return httpx.Response(200, json=call("check_allocation", args, 1))
        return httpx.Response(200, json=answer(proposal(items["t510"].id, items["adata"].id), 2))

    planner = planner_for(settings, httpx.MockTransport(handler))
    items.update(demo_drawer(planner.inventory))
    [project] = await planner.propose(ProposeRequest(count=1))
    first, second = bodies
    assert [t["name"] for t in first["tools"]][-1] == "check_allocation"
    assert "check_allocation" in first["instructions"]
    result = next(i for i in second["input"] if i["type"] == "function_call_output")
    seen = json.loads(result["output"])
    [refused] = seen["refused"]
    assert refused["item_id"] == items["hynix"].id
    assert refused["reason"] == "incompatible: DDR4 SO-DIMM in a DDR3 laptop (ThinkPad T510)"
    assert refused["fits_instead"] == [{"item_id": items["adata"].id, "name": "ADATA 8 GB"}]
    assert refused["needs"] == "DDR3 SO-DIMM laptop memory"
    # the model took the other stick: kept, and the pairing passes
    assert {a.item_id for a in project.allocations} == {items["t510"].id, items["adata"].id}
    assert [p.state for p in project.compatibility] == ["pass"] and not project.dropped


async def test_a_pick_that_slips_through_is_dropped_with_its_reason(
    live_settings: Settings,
) -> None:
    # without the rules in the request, the tools and the instructions are as they were
    items: dict[str, Item] = {}
    bodies: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json=answer(proposal(items["t510"].id, items["hynix"].id), 1))

    off = live_settings.model_copy(update={"compat_prompts": False})
    planner = planner_for(off, httpx.MockTransport(handler))
    items.update(demo_drawer(planner.inventory))
    [project] = await planner.propose(ProposeRequest(count=1))
    assert [t["name"] for t in bodies[0]["tools"]] == [
        "list_inventory",
        "template_catalog",
        "item_details",
    ]
    assert "check_allocation" not in bodies[0]["instructions"]
    assert [a.item_id for a in project.allocations] == [items["t510"].id]
    assert project.dropped == [
        "memory: SK hynix 8 GB incompatible: DDR4 SO-DIMM in a DDR3 laptop (ThinkPad T510)"
    ]
    memory = next(r for r in project.requirements if r.key == "memory")
    assert memory.state == "unknown"
    assert memory.incompatible == "incompatible: DDR4 SO-DIMM in a DDR3 laptop (ThinkPad T510)"
    assert memory.need == "DDR3 SO-DIMM laptop memory"
    assert (memory.instead_id, memory.instead) == (items["adata"].id, "ADATA 8 GB")
    # the stick is refused by hand too; the one that fits is taken
    with pytest.raises(ProjectsError, match="does not fit this build: DDR4 SO-DIMM"):
        planner.fill(project.id, "memory", FillRequest(item_id=items["hynix"].id))
    filled = planner.fill(project.id, "memory", FillRequest(item_id=items["adata"].id))
    memory = next(r for r in filled.requirements if r.key == "memory")
    assert memory.state == "pass" and memory.incompatible == "" and memory.need == ""
    assert [p.state for p in filled.compatibility] == ["pass"]
    # the pack says it
    planner.select(project.id)
    pack = planner.write_pack(project.id)
    assert (
        "## Compatibility" in pack.markdown
        and "- pass: ADATA 8 GB with ThinkPad T510" in pack.markdown
    )


async def test_the_missing_part_becomes_a_search_for_what_fits(live_settings: Settings) -> None:
    items: dict[str, Item] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=answer(proposal(items["t510"].id, items["hynix"].id), 1))

    on = live_settings.model_copy(update={"compat_prompts": True})
    planner = planner_for(on, httpx.MockTransport(handler))
    items.update(demo_drawer(planner.inventory))
    # the stick that would fit is for sale: nothing of the owner's fills it
    planner.inventory.update(items["adata"].id, ItemPatch(intent="sell"))
    # no check_allocation call here: the answer comes at once, and the rules drop the stick
    [project] = await planner.propose(ProposeRequest(count=1))
    searched = planner.search_for(project.id, "memory")
    req = next(r for r in searched.requirements if r.key == "memory")
    assert req.search_id is not None and req.instead == ""
    title = planner.finder.search(req.search_id).title
    assert title == "DDR3 SO-DIMM laptop memory for Home automation on the T510"


def test_the_pack_names_no_other_item_of_the_owner_s_to_the_visitor() -> None:
    markdown = "\n".join(
        [
            "## Still needed",
            "",
            "- RAM (optional); what fits: DDR3 SO-DIMM; yours that fits: Grandma's stick",
            "",
            "## Compatibility",
            "",
            "- fail: A with B: DDR4 in a DDR3 laptop; use Grandma's stick instead, it fits",
            "",
        ]
    )
    shown = visitor_markdown(markdown)
    assert "Grandma" not in shown and "what fits: DDR3 SO-DIMM" in shown
    assert "- fail: A with B: DDR4 in a DDR3 laptop" in shown


# --- an allocation swapped or taken off by hand ------------------------------------------------


def test_an_allocation_is_swapped_or_taken_off_by_the_owner(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        planner: Planner = client.app.state.planner  # type: ignore[attr-defined]
        items = demo_drawer(planner.inventory)
        row = planner.inventory.add_project(
            "home_automation_server",
            "Laptop server",
            json.dumps(
                {
                    "result": "r",
                    "requirements": [
                        {
                            "key": r.key,
                            "label": r.label,
                            "kind": r.kind,
                            "blocking": r.blocking,
                            "state": "pass" if r.key in ("server", "memory") else "unknown",
                            "item_id": {
                                "server": items["t510"].id,
                                "memory": items["hynix"].id,
                            }.get(r.key),
                            "search_id": None,
                            "profile": r.profile,
                        }
                        for r in planner.templates.get("home_automation_server").requirements
                    ],
                    "effort": "medium",
                    "skills": [],
                    "spend_estimate": 0,
                    "currency": "USD",
                    "unknowns": [],
                    "sources": [],
                    "steps": ["one"],
                    "safety": [],
                    "dropped": [],
                    "model": "m",
                    "from_fixture": True,
                    "cost_usd": 0.0,
                }
            ),
            [(items["t510"].id, "server", "on"), (items["hynix"].id, "memory", "more")],
        )
        pid = int(row["id"])
        shown = client.get(f"/api/projects/{pid}").json()
        assert [p["state"] for p in shown["compatibility"]] == ["fail"]
        assert shown["compatibility"][0]["fix"] == "use ADATA 8 GB instead, it fits"
        client.post(f"/api/projects/{pid}/select", json={})
        assert planner.inventory.get(items["hynix"].id).availability == "reserved"
        # a swap for something that is not the kind, or does not fit, is refused and says why
        bad = client.patch(
            f"/api/projects/{pid}/allocations/{items['hynix'].id}",
            json={"item_id": items["monitor"].id},
        )
        assert bad.status_code == 422 and "not a kind" in bad.json()["detail"]
        swapped = client.patch(
            f"/api/projects/{pid}/allocations/{items['hynix'].id}",
            json={"item_id": items["adata"].id, "why": "the DDR3L one"},
        )
        assert swapped.status_code == 200, swapped.text
        body = swapped.json()
        assert {a["item_id"] for a in body["allocations"]} == {items["t510"].id, items["adata"].id}
        assert [p["state"] for p in body["compatibility"]] == ["pass"]
        # the stick taken off is free again; the one put on is held
        assert planner.inventory.get(items["hynix"].id).availability == "available"
        assert planner.inventory.get(items["adata"].id).availability == "reserved"
        # back to the stick that does not fit: refused
        refused = client.patch(
            f"/api/projects/{pid}/allocations/{items['adata'].id}",
            json={"item_id": items["hynix"].id},
        )
        assert (
            refused.status_code == 422
            and "DDR4 SO-DIMM in a DDR3 laptop" in refused.json()["detail"]
        )
        assert (
            client.patch(
                f"/api/projects/{pid}/allocations/999", json={"item_id": items["hynix"].id}
            ).status_code
            == 404
        )
        removed = client.delete(f"/api/projects/{pid}/allocations/{items['adata'].id}")
        assert removed.status_code == 200
        memory = next(r for r in removed.json()["requirements"] if r["key"] == "memory")
        assert memory["state"] == "unknown" and memory["item_id"] is None
        assert planner.inventory.get(items["adata"].id).availability == "available"
        # a build under way keeps what it blocks on
        client.post(f"/api/projects/{pid}/advance/building")
        kept = client.delete(f"/api/projects/{pid}/allocations/{items['t510'].id}")
        assert kept.status_code == 422 and "blocks the build" in kept.json()["detail"]


def test_the_demo_visitor_cannot_swap_or_remove(tmp_path: Path) -> None:
    from tests.test_gate import gated_settings

    with TestClient(create_app(gated_settings(tmp_path))) as gated:
        assert gated.patch("/api/projects/1/allocations/2", json={"item_id": 3}).status_code == 403
        assert gated.delete("/api/projects/1/allocations/2").status_code == 403


# --- Decide: the cards' "with what you have" --------------------------------------------------


def test_a_reuse_card_loses_the_part_that_does_not_fit_and_says_what_to_search(
    settings: Settings,
) -> None:
    inv = Inventory(settings)
    board = make(inv, "motherboard", "ASUS P8Z77-V LX motherboard", model_number="P8Z77-VLX")
    make(inv, "processor", "Intel slot 1 processor with its fan")
    make(inv, "graphics card", "EVGA 9800 GT", connector="pci-e")
    card = {
        "title": "Learning bench",
        "what_it_does": "a board to learn the parts on",
        "with_items": ["processor (1)", "graphics card (1)"],
        "difficulty": "easy",
        "why": "w",
        "extra_parts": [],
        "cost": "0",
        "time": "1 h",
    }
    content = {
        "profiled": False,
        "keep_fix": {
            "worth_fixing": False,
            "problems": [],
            "steps": [],
            "difficulty": "easy",
            "why": "",
            "parts": [],
            "cost": "",
            "time": "",
        },
        "reuse": [card],
        "sell": {"selling_points": [], "effort": "", "note": ""},
        "recommended": "reuse",
        "reason": "r",
        "model": "m",
        "from_fixture": True,
        "cost_usd": 0.0,
    }
    inv.add_scenarios(board.id, json.dumps(content), item_version=board.version)
    decider = Decider(
        settings,
        cast(ModelApiClient, None),
        inv,
        Templates(),
        cast(Planner, None),
        cast(Any, None),
        cast(Any, None),
    )
    read = decider.latest_scenarios(board.id)
    assert read is not None
    [reuse] = read.reuse
    assert reuse.with_items == ["graphics card"] and reuse.without == ["processor"]
    states = {p.part: p.state for p in reuse.compatibility}
    assert states == {"Intel slot 1 processor with its fan": "fail", "EVGA 9800 GT": "pass"}
    fail = next(p for p in reuse.compatibility if p.state == "fail")
    assert fail.reason == "a Slot 1 processor does not fit an LGA1155 board"
    assert fail.fix == "needs an LGA1155 processor — not in your inventory; search it"
    # the stored row stays as the model wrote it
    stored = json.loads(inv.scenarios(board.id)[-1]["content"])
    assert stored["reuse"][0]["with_items"] == ["processor (1)", "graphics card (1)"]
    # with the rules in the request, the brief carries the pairings
    on = settings.model_copy(update={"compat_prompts": True})
    lines = Decider(
        on,
        cast(ModelApiClient, None),
        inv,
        Templates(),
        cast(Planner, None),
        cast(Any, None),
        cast(Any, None),
    ).fits_for(inv.get(board.id))
    assert lines[0].startswith("fail: Intel slot 1 processor with its fan with ASUS P8Z77-V LX")
