# Compatibility rules

A kind is not a fit. A requirement that takes *memory* is filled by any stick, but a DDR4 laptop
stick does not go in a laptop that takes DDR3, a Slot 1 Pentium fits no LGA1155 board, an
Arduino and its modules do not go inside an M.2 SSD enclosure, and an M.2 to U.2 adapter is
no use without a U.2 drive. The compatibility rules check that parts physically work together,
by the values the app holds, with no model call. Each pairing answers **pass**, **fail** or
**unknown**; an unknown is a question to check, never a pass.

## Built so far

**Data, not code.** Two YAML files under `backend/app/compat/data/`:

- `roles.yaml`: the part an item plays, read from its type as a template reads kinds (the type
  ends in one of the kinds, as whole words): memory, processor, board, laptop, drive, adapter,
  enclosure, card, controller (a microcontroller board) and module. A type listed under `not`
  plays none (a *powerline adapter* is no drive adapter). A role's `defaults` are what the type
  alone says (a laptop takes SO-DIMM sticks), its `hints` what words in the type or the name add
  (a *laptop motherboard* takes SO-DIMMs, *desktop memory* is a DIMM).
- `parts.yaml`: parts known by their model or part number, with what their label does not
  print: the three desktop boards of the demo set (socket, memory, form, slots), the ThinkPad
  T510 by its machine type, and the memory makers' part-number schemes (SK hynix `HMA...S6` is a
  DDR4 SO-DIMM, `HMT` DDR3; G.Skill `F3-` is DDR3, `F4-` DDR4; ADATA `AM1L` DDR3L SO-DIMM, `AO1P`
  DDR4 SO-DIMM; Ramaxel `RMSA` DDR4 SO-DIMM; Patriot `PV3`/`PVE4`), the Kingston A400 and the
  Toshiba MQ01 drives, the UNO R3's 5 V logic. Only what the maker documents is written there.

**Where the values come from**, first found first: a field that states the value outright
(`memory_type`, `socket`, `drive_form`, `holds` and the like), the known part its model or part
number (or its name) is, what its accepted values say, its name, then its type. The readers
(`backend/app/compat/normalize.py`) spell every value one way:

| Written | Read as |
|---|---|
| `PC3-12800`, `DDR3-1600` | DDR3 |
| `PC3L-12800`, `DDR3L` | DDR3L |
| `PC4-2666`, `DDR4-2666` | DDR4 |
| `SO-DIMM 260-pin` | DDR4 SO-DIMM |
| `204-pin` | DDR3 SO-DIMM |
| `240-pin`, `288-pin` | DIMM (the generation is shared, so it stays unknown) |
| `LPDDR4` | nothing: soldered memory is no module |
| `LGA1155`, `FCLGA1155`, `Socket 1155` | LGA1155 |
| `socket AM4`, `Slot 1`, `Socket 370` | AM4, Slot 1, Socket 370 |
| `Micro-ATX`, `mini-ITX` | mATX, ITX |
| `2.5"`, `3.5 inch` | 2.5, 3.5 |
| `M.2 and mSATA to SATA adapter` | takes M.2 and mSATA drives, plugs into SATA |
| `M.2 to U.2 adapter` | takes a U.2 drive, plugs into an M.2 slot |
| `M.2 SSD to USB enclosure` | takes an M.2 drive |
| `2.5 to 3.5 inch adapter`, `M.2 to 2.5 inch SATA adapter` | takes a 2.5 inch drive into a 3.5 inch bay; an M.2 drive in a 2.5 inch SATA shell |
| `mini-PCIe card` | no bus: a mini-PCIe card is no desktop PCIe card |

**The pairings.** One rule per pair of roles (`backend/app/compat/rules.py`):

| Part | Host | Passes when | Fails when |
|---|---|---|---|
| memory | board, laptop | the generation and the form are known and match (DDR3L in a DDR3 slot passes: it runs at 1.5 V too) | the generation or the form differs: *DDR4 SO-DIMM in a DDR3 laptop* |
| processor | board | the sockets match | they differ: *a Slot 1 processor does not fit an LGA1155 board* |
| drive | laptop | a 2.5 inch drive of the bay's interface | a 3.5 inch or U.2 drive |
| drive | board | a SATA drive and SATA ports, an M.2 drive and an M.2 slot | the board has no port or slot of its kind |
| drive | adapter, enclosure | its form is one the holder takes | it is not: *a 2.5 inch drive in an enclosure that takes M.2 drives* |
| card | board | its bus is one of the board's slots | an AGP card on a PCIe board |
| adapter | board | what it plugs into is on the board | it is not |
| module, controller | enclosure | it fits inside by its measured size | the enclosure is made for drives only, or it is larger |
| module | controller | both logic levels are known and match | a 5 V module on a 3.3 V board |

A value missing on either side is **unknown**: *check which memory Dell laptop, opened takes
(not recorded)*. In a set of items each part is paired with the host that suits it best (a pass
over an unknown over a fail), so a SATA drive on the board's ports is not failed by the M.2
card beside it. An adapter or an enclosure with no drive of its kind in the set is a **missing
part**: *nothing you own goes in it: it takes an M.2 drive*.

**The fix of a failure.** An item of yours that fits in place of the one that fails (*use ADATA 8
GB DDR3L laptop memory instead, it fits*), else the part to search for (*needs an LGA1155
processor — not in your inventory; search it*), with a Marketplace search for it. The fix is on
the side the rule says: the stick rather than the laptop, the project box rather than the
module.

**Where they apply.**

- [Build and reuse](../guides/reuse.md): a proposal keeps only the picks that work together
  (blocking requirements first, so the laptop stays and the stick that does not fit it goes),
  and says why in the requirement and in what was left out; **Use it** and a swap by hand are
  refused the same way; every project lists its pairings, and its build pack has a
  *Compatibility* section.
- [Decide](../guides/decide.md): each reuse card's *With what you have* is checked against what
  you own; a kind none of whose items works with the rest is taken out and named, with its fix;
  each idea lists the pairings of what it names.
- The models are told too (`COMPAT_PROMPTS`, on by default): the proposals' tool loop has a
  `check_allocation` tool that refuses an incompatible pick with the reason and what would fit
  in its place, the inventory it lists carries each item's values, the Decide briefs carry the
  item's pairings, and a missing requirement's search names the part that fits (*DDR3 SO-DIMM
  laptop memory for ...*). `COMPAT_PROMPTS=0` leaves them out; the rules check every result
  either way.

## Not yet

- Physical size inside a case, power supply wattage and connectors, a cooler's mount, a
  laptop's own M.2 or mSATA slot: unknown until a part's values say.
- A part not in `parts.yaml` is read from its values alone; a board or a laptop without a known
  model stays unknown for its socket and memory.
