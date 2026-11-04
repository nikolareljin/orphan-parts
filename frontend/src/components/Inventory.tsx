import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { api, type Item, type ItemEvent, type ItemSummary, type JudgeAccess, type PhotoPrivacy, type PrivacyArea, type ProfileSummary, type Provenance } from '../lib/api'
import { fieldLabel, percent, printedDiffers, withUnit } from '../lib/format'
import { AVAILABILITIES, INTENTS, PROVENANCES, asksForParent, availabilityLabel, cameFrom, photoReadLine, changedDetails, isConflict, mergeDetails, planLabel, proposedCount, provenanceLabel, reviewLabel, savedLabel, whenText } from '../lib/inventory'
import Assess from './Assess'
import Decide from './Decide'
import GatedImage from './GatedImage'
import Listing from './Listing'
import Modal from './Modal'
import ParentPrompt from './ParentPrompt'
import Measure from './Measure'
import { ItemSearch } from './SearchPlan'
import Picture from './Picture'
import SectionNav, { type SectionEntry } from './SectionNav'
import Value from './Value'
import HelpTip from './HelpTip'
import { HELP } from '../lib/help'
import { JUDGE_LOCKED, judgeMayChange } from '../lib/access'

function message(err: unknown): string {
  return err instanceof Error ? err.message : String(err)
}

// The item dialog's sections, in the order they are laid out; the bar at the top links to them.
const SECTIONS: SectionEntry[] = [
  { id: 'facts', label: 'Facts' },
  { id: 'decide', label: 'Decide' },
  { id: 'value', label: 'Value' },
  { id: 'sell', label: 'Sell or give away' },
  { id: 'fit', label: 'Measure and fit' },
  { id: 'picture', label: 'Picture' },
]

// The owner's items. ``refresh`` changes when something was saved elsewhere on the page.
export default function Inventory({
  refresh,
  openId: wanted = null,
  onOpened,
  demo = false,
  samplesOnly = demo,
  judge = null,
}: {
  refresh: number
  openId?: number | null
  onOpened?: () => void
  demo?: boolean
  // no upload input (voice note, measure photo) until uploads are known to be open
  samplesOnly?: boolean
  // a judge's code: only the items it added are its to change
  judge?: JudgeAccess | null
}) {
  const [items, setItems] = useState<ItemSummary[] | null>(null)
  const [openId, setOpenId] = useState<number | null>(wanted)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    try {
      setItems(await api.items.list())
      setError('')
    } catch (err: unknown) {
      setError(message(err))
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load, refresh])

  // an item opened from elsewhere (the inbox) is shown as soon as it is asked for, once:
  // the ask is handed back as taken, so the next visit to the page does not reopen it
  useEffect(() => {
    if (wanted !== null) {
      setOpenId(wanted)
      onOpened?.()
    }
  }, [wanted, refresh, onOpened])

  return (
    <section className="inventory">
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {items === null && !error && <p className="muted">Loading…</p>}
      {items !== null && items.length === 0 && (
        <p className="muted">No items yet. Read a label and save it, or read a capture in the Inbox, to add one.</p>
      )}
      {items !== null && items.length > 0 && (
        <table className="items" aria-label="Items">
          <thead>
            <tr>
              <th scope="col">Item</th>
              <th scope="col">Fields</th>
              <th scope="col">Plan</th>
              <th scope="col">Saved results</th>
              <th scope="col">Availability</th>
              <th scope="col">Updated</th>
              <th scope="col">
                <span className="visually-hidden">Open</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {items.map((s) => (
              <tr key={s.id} className={s.id === openId ? 'open' : undefined}>
                <th scope="row">
                  {s.name}
                  {s.parent_id !== null && <span className="muted"> (part of #{s.parent_id})</span>}
                  {s.item_type !== s.name && <span className="raw">{s.item_type}</span>}
                </th>
                <td>{s.field_count}</td>
                <td>{planLabel(s)}</td>
                <td>
                  {(s.saved ?? []).length === 0 ? (
                    <span className="muted">none</span>
                  ) : (
                    <ul className="saved-marks" aria-label={`Saved for ${s.name}`}>
                      {(s.saved ?? []).map((k) => (
                        <li key={k} className="badge">
                          {savedLabel(k)}
                        </li>
                      ))}
                    </ul>
                  )}
                </td>
                <td>{availabilityLabel(s.availability)}</td>
                <td>{whenText(s.updated_at)}</td>
                <td>
                  <button type="button" className="link" onClick={() => setOpenId(s.id)}>
                    Open
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {openId !== null && (
        <Modal title={`Item #${openId}`} onClose={() => setOpenId(null)}>
          <ItemPanel
            key={openId}
            id={openId}
            demo={demo}
            samplesOnly={samplesOnly}
            judge={judge}
            onChanged={() => void load()}
            onClosed={() => {
              setOpenId(null)
              void load()
            }}
          />
        </Modal>
      )}
    </section>
  )
}

function ItemPanel({
  id,
  demo,
  samplesOnly,
  judge = null,
  onChanged,
  onClosed,
}: {
  id: number
  demo: boolean
  samplesOnly: boolean
  judge?: JudgeAccess | null
  onChanged: () => void
  onClosed: () => void
}) {
  const [item, setItem] = useState<Item | null>(null)
  const [events, setEvents] = useState<ItemEvent[] | null>(null)
  const [error, setError] = useState('')
  const [details, setDetails] = useState({ condition: '', faults: '', tests_done: '', accessories: '', location: '', notes: '' })
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [profiles, setProfiles] = useState<ProfileSummary[]>([])
  // a guidance written on the Value panel or the Decide panel's sell card: both read it again
  const [guided, setGuided] = useState(0)

  useEffect(() => {
    let cancelled = false
    api.profiles
      .list()
      .then((list) => {
        if (!cancelled) setProfiles(list)
      })
      .catch(() => {
        if (!cancelled) setProfiles([])
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    setItem(null)
    setEvents(null)
    setConfirmDelete(false)
    api.items
      .get(id)
      .then((it) => {
        if (cancelled) return
        setItem(it)
        setDetails({
          condition: it.condition,
          faults: it.faults,
          tests_done: it.tests_done,
          accessories: it.accessories,
          location: it.location,
          notes: it.notes,
        })
        setError('')
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(message(err))
      })
    return () => {
      cancelled = true
    }
  }, [id])

  // The server's item, with what the owner typed in the details and has not saved kept as typed;
  // a save of the details (``saved``) takes the server's values as they were kept.
  function show(next: Item, saved = false) {
    const before = saved ? null : item
    setItem(next)
    setDetails((typed) => mergeDetails(typed, before, next))
    setEvents(null)
  }

  // Every change goes through here: the item is replaced by the server's answer, the list reloads.
  // A write refused because the item changed in between reloads it instead of overwriting.
  // The refusal is shown here and thrown again, so a panel with its own error line says it too
  // and does not carry on as if the change had happened.
  async function apply(action: () => Promise<Item>, saved = false) {
    try {
      show(await action(), saved)
      setError('')
      onChanged()
    } catch (err: unknown) {
      if (isConflict(err)) {
        try {
          show(await api.items.get(id))
          setError(`${message(err)}. The item changed meanwhile and was reloaded; make your change again if it still applies.`)
          throw err
        } catch (reloadErr: unknown) {
          if (reloadErr === err) throw err
          // the reload failed too: the original message stands
        }
      }
      setError(message(err))
      throw err
    }
  }

  // The same for a control with nowhere of its own to say a refusal: the error line above says it.
  function attempt(action: () => Promise<Item>, saved = false) {
    void apply(action, saved).catch(() => undefined)
  }

  async function showEvents() {
    try {
      setEvents(await api.items.events(id))
    } catch (err: unknown) {
      setError(message(err))
    }
  }

  async function remove() {
    try {
      await api.items.remove(id)
      onClosed()
    } catch (err: unknown) {
      setError(message(err))
    }
  }

  if (item === null) {
    return (
      <div className="item">
        {error ? (
          <p className="error" role="alert">
            {error}
          </p>
        ) : (
          <p className="muted">Loading item #{id}…</p>
        )}
      </div>
    )
  }

  const fields = Object.values(item.fields)
  const toConfirm = proposedCount(item)
  // the demo, or an item served as the demo visitor sees it (a session that ended unnoticed):
  // the details are shown, never saved
  // and, for a judge's code, an item it did not add (the server refuses those writes anyway)
  const judgeLocked = !judgeMayChange(judge, item)
  const readOnly = demo || item.redacted === true || judgeLocked
  const detailsChanged = (Object.keys(details) as (keyof typeof details)[]).some((k) => details[k] !== item[k])

  return (
    <article className="item" aria-label={`Item ${item.name}`}>
      <h3>
        {item.name} <span className="badge">#{item.id}</span>
      </h3>
      <p className="meta">
        {item.item_type} · version {item.version} · saved {whenText(item.created_at)}
        {item.parent_id !== null && <> · part of item #{item.parent_id}</>}
      </p>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <SectionNav entries={SECTIONS} />

      <div className="item-section" data-section="facts">
        <div className="section-head">
          <h4>Facts</h4>
          <HelpTip entry={readOnly ? HELP.factsVisitor : HELP.facts} />
        </div>
        {asksForParent(item) ? (
          <ParentPrompt item={item} readOnly={readOnly} save={(action) => apply(action)} />
        ) : (
          cameFrom(item) && (
            <div className="came-from-block">
              <p className="meta came-from">{cameFrom(item)}</p>
              {photoReadLine(item) && <p className="meta photo-read">{photoReadLine(item)}</p>}
              {/* the device's photos are the owner's: the demo visitor is never sent them */}
              {!readOnly && <ItemPhotos key={`device-${item.version}`} id={item.id} device />}
            </div>
          )
        )}
        <ItemPhotos key={item.version} id={item.id} owner={!readOnly} />
        <div className="row">
          <label>
            <span>Plan</span>
            <select
              disabled={readOnly}
              value={item.intent}
              onChange={(e) =>
                attempt(() =>
                  api.items.update(item.id, { intent: e.target.value as Item['intent'], version: item.version }),
                )
              }
            >
              {INTENTS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>Availability</span>
            <select
              disabled={readOnly}
              value={item.availability}
              onChange={(e) =>
                attempt(() =>
                  api.items.update(item.id, {
                    availability: e.target.value as Item['availability'],
                    version: item.version,
                  }),
                )
              }
            >
              {AVAILABILITIES.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>Profile</span>
            <select
              disabled={readOnly}
              value={item.profile}
              onChange={(e) => attempt(() => api.items.update(item.id, { profile: e.target.value, version: item.version }))}
            >
              <option value="">not set</option>
              {profiles.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.label}
                </option>
              ))}
            </select>
          </label>
        </div>

        <h4>
          Fields
          {toConfirm > 0 && <span className="badge">{toConfirm} to confirm</span>}
        </h4>
        {fields.length === 0 ? (
          <p className="muted">No fields yet.{!readOnly && ' Add one below under Add what you know.'}</p>
        ) : (
          <div className="table-wrap">
            <table className="evidence" aria-label="Fields">
              <thead>
                <tr>
                  <th scope="col">Field</th>
                  <th scope="col">Value</th>
                  <th scope="col">Known from</th>
                  <th scope="col">Review</th>
                </tr>
              </thead>
              <tbody>
                {fields.map((a) => (
                  <tr key={a.id}>
                    <th scope="row">{fieldLabel(a.field)}</th>
                    <td>
                      {withUnit(a)}
                      {printedDiffers(a.value, a.raw) && <span className="raw">as printed: {a.raw}</span>}
                    </td>
                    <td>
                      {provenanceLabel(a.provenance)}
                      {a.provenance === 'observed' && <span className="raw">{percent(a.confidence)} confidence</span>}
                    </td>
                    <td>
                      {reviewLabel(a.review)}
                      {a.review === 'proposed' && !readOnly && (
                        <span className="actions">
                          <button type="button" className="link" onClick={() => attempt(() => api.items.review(item.id, a.id, 'accepted'))}>
                            Accept
                          </button>
                          <button type="button" className="link" onClick={() => attempt(() => api.items.review(item.id, a.id, 'rejected'))}>
                            Reject
                          </button>
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {!readOnly && <AddField onAdd={(spec) => apply(() => api.items.addField(item.id, spec))} />}

        <form
          className="details"
          onSubmit={(e: FormEvent) => {
            e.preventDefault()
            // only what was changed, and nothing from a demo load: a blank it was served is not
            // the owner's value, and a session opened meanwhile would write it over theirs
            if (readOnly) return
            attempt(() => api.items.update(item.id, { ...changedDetails(details, item), version: item.version }), true)
          }}
        >
          <h4>Details</h4>
          {(
            [
              ['condition', 'Condition'],
              ['faults', 'Known faults'],
              ['tests_done', 'Tests done'],
              ['accessories', 'Included accessories'],
              ['location', 'Where it is kept (private)'],
              ['notes', 'Notes (private)'],
            ] as const
          )
            // the owner's alone: the demo visitor is never sent them, so there is nothing to show
            .filter(([key]) => !readOnly || (key !== 'location' && key !== 'notes'))
            .map(([key, label]) => (
              <label key={key}>
                <span>{label}</span>
                <textarea name={key} rows={1} readOnly={readOnly} value={details[key]} onChange={(e) => setDetails({ ...details, [key]: e.target.value })} />
              </label>
            ))}
          {readOnly ? (
            <p className="meta">{judgeLocked ? `${JUDGE_LOCKED}.` : 'Shown as in the public demo; sign in with the code to edit the details.'}</p>
          ) : (
            <button type="submit" disabled={!detailsChanged}>
              Save details
            </button>
          )}
        </form>

        {!readOnly && (
          <AddComponent
            onAdd={(spec) =>
              apply(async () => {
                // the part is its own record; this page stays on the whole and shows what left
                await api.items.addComponent(item.id, spec)
                return api.items.get(item.id)
              })
            }
          />
        )}
        {item.components.length > 0 && (
          <p className="meta">Separated parts: {item.components.map((c) => `#${c}`).join(', ')}</p>
        )}
      </div>

      <div className="item-section" data-section="decide">
        <Decide
          item={item}
          guided={guided}
          onDecide={(choice, note) => apply(() => api.decide.choose(item.id, choice, note, item.version))}
          onGuided={() => setGuided((n) => n + 1)}
          demo={demo}
          readOnly={readOnly}
        />
      </div>

      <div className="item-section" data-section="value">
        <Value item={item} refresh={guided} onGuided={() => setGuided((n) => n + 1)} readOnly={readOnly} />
      </div>

      <div className="item-section" data-section="sell">
        <Listing item={item} readOnly={readOnly} samplesOnly={samplesOnly} onChanged={() => attempt(() => api.items.get(item.id))} />
      </div>

      <div className="item-section" data-section="fit">
        <Measure item={item} demo={samplesOnly} onMeasured={() => attempt(() => api.items.get(item.id))} />
        <Assess item={item} />
        {!demo && <ItemSearch item={item} />}
      </div>

      {/* the wrapper stays empty, and hidden, when there is no picture to show */}
      <div className="item-section" data-section="picture">
        <Picture item={item} demo={demo || judgeLocked} />
      </div>

      <div className="item-footer">
        <span className="check-with-help">
          <label className="check">
            <input
              type="checkbox"
              checked={item.public}
              disabled={readOnly || judge !== null}
              title={judge !== null ? 'Judge access: what you add stays out of the public demo' : undefined}
              onChange={(e) => attempt(() => api.items.setPublic(item.id, e.target.checked))}
            />
            <span>
              Show in the public demo{' '}
              <small className="muted">Visitors without the access code can open this item, its photos and drawings. Location and notes stay private.</small>
            </span>
          </label>
          <HelpTip entry={HELP.publicDemo} />
        </span>
        <span className="item-actions">
          {/* the owner's alone: the history carries the notes said with each decision */}
          {!readOnly && (
            <button type="button" className="link" onClick={() => void showEvents()}>
              History
            </button>
          )}
          {confirmDelete ? (
            <button type="button" className="danger" onClick={() => void remove()}>
              Yes, delete item #{item.id}
            </button>
          ) : (
            <button
              type="button"
              className="danger quiet"
              disabled={readOnly}
              title={judgeLocked ? JUDGE_LOCKED : readOnly ? 'The demo set cannot be deleted' : undefined}
              onClick={() => setConfirmDelete(true)}
            >
              Delete
            </button>
          )}
        </span>
      </div>
      {events !== null && (
        <ol className="events" aria-label="History">
          {events.map((ev) => (
            <li key={ev.id}>
              <span className="muted">{whenText(ev.at)}</span> {ev.change}
            </li>
          ))}
        </ol>
      )}
    </article>
  )
}

// The photos the item was read from (the capture's, or the label photos saved with it), a row
// of thumbnails above the values to confirm, so each value can be checked against the picture.
// One click makes a photo large, another shrinks it. Each photo says what was hidden on the
// copies that leave the owner's view; the owner sees the original with those areas outlined,
// and can show an area that is nothing private after all, or hide it again.
function ItemPhotos({ id, device = false, owner = false }: { id: number; device?: boolean; owner?: boolean }) {
  const [count, setCount] = useState<number | null>(null)
  const [checks, setChecks] = useState<PhotoPrivacy[]>([])
  const [big, setBig] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)
  const [problem, setProblem] = useState('')

  useEffect(() => {
    let cancelled = false
    setCount(null)
    setBig(null)
    const counted = device ? api.items.devicePhotos(id) : api.items.photos(id)
    counted
      .then((p) => {
        if (cancelled) return
        setCount(p.count)
        setChecks(p.photos ?? [])
      })
      .catch(() => {
        if (!cancelled) setCount(-1) // not known: nothing is said either way
      })
    return () => {
      cancelled = true
    }
  }, [id, device])

  async function checkAgain() {
    setBusy(true)
    setProblem('')
    try {
      const p = await api.items.checkPhotos(id)
      setChecks(p.photos ?? [])
    } catch (err: unknown) {
      setProblem(message(err))
    } finally {
      setBusy(false)
    }
  }

  async function choose(n: number, area: PrivacyArea) {
    setProblem('')
    try {
      const updated = await api.items.chooseArea(id, n, area.id, !area.hidden)
      setChecks((all) => all.map((c) => (c.n === n ? updated : c)))
    } catch (err: unknown) {
      setProblem(message(err))
    }
  }

  if (count === null || count < 0) return null
  if (count === 0) return device ? null : <p className="muted no-photos">No photos saved with this item.</p>
  const byN = new Map(checks.map((c) => [c.n, c]))
  const waiting = checks.some((c) => !c.shared)
  const opened = big !== null ? byN.get(big) : undefined
  return (
    <div className="item-photos-block">
      <div className="item-photos" aria-label={device ? 'Photos of the device' : 'Photos'}>
        {Array.from({ length: count }, (_, i) => i + 1).map((n) => (
          <button
            key={n}
            type="button"
            className={`link photo${big === n ? ' open' : ''}`}
            title={big === n ? 'Shrink' : 'Enlarge'}
            onClick={() => setBig(big === n ? null : n)}
          >
            <span className="photo-frame">
              <GatedImage src={device ? api.items.devicePhotoUrl(id, n) : api.items.photoUrl(id, n)} alt={device ? `Device photo ${n}` : `Item photo ${n}`} loading="lazy" />
              {/* the owner sees the original: on the opened photo, the areas hidden on shared
                  copies are outlined (a thumbnail is cropped square, so not there) */}
              {owner &&
                big === n &&
                (byN.get(n)?.areas ?? []).map((a) => (
                  <span
                    key={a.id}
                    aria-hidden="true"
                    className={`privacy-box${a.hidden ? '' : ' shown'}`}
                    style={{ left: `${a.x * 100}%`, top: `${a.y * 100}%`, width: `${a.w * 100}%`, height: `${a.h * 100}%` }}
                    title={`${a.label}: ${a.hidden ? 'hidden when shared' : 'shown by you'}`}
                  />
                ))}
            </span>
          </button>
        ))}
      </div>
      {!device && checks.length > 0 && (
        <div className="privacy-row">
          <ul className="privacy-notes" aria-label="Private details">
            {checks.map((c) => (
              <li key={c.n} className={`privacy-note ${c.status}`}>
                {count > 1 && <span className="muted">Photo {c.n}: </span>}
                {c.note}
              </li>
            ))}
          </ul>
          <HelpTip entry={owner ? HELP.photos : HELP.photosVisitor} />
        </div>
      )}
      {owner && opened && opened.areas.length > 0 && (
        <div className="privacy-areas" aria-label={`Areas on photo ${opened.n}`}>
          {opened.areas.map((a) => {
            // two areas of one kind (two MAC addresses) are told apart by their number
            const same = opened.areas.filter((b) => b.label === a.label)
            const which = same.length > 1 ? ` ${same.indexOf(a) + 1}` : ''
            return (
              <button key={a.id} type="button" className="secondary" onClick={() => void choose(opened.n, a)}>
                {a.hidden ? `Show ${a.label}${which}` : `Hide ${a.label}${which}`}
              </button>
            )
          })}
        </div>
      )}
      {owner && waiting && (
        <button type="button" className="secondary" disabled={busy} onClick={() => void checkAgain()}>
          {busy ? 'Checking…' : 'Check for private details'}
        </button>
      )}
      {problem && (
        <p className="error" role="alert">
          {problem}
        </p>
      )}
    </div>
  )
}

function AddField({ onAdd }: { onAdd: (spec: { field: string; value: string; unit: string; provenance: Provenance }) => Promise<void> }) {
  const [field, setField] = useState('')
  const [value, setValue] = useState('')
  const [unit, setUnit] = useState('')
  const [provenance, setProvenance] = useState<Provenance>('owner_reported')
  const name = field.trim().toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '')
  return (
    <form
      className="inline"
      onSubmit={(e: FormEvent) => {
        e.preventDefault()
        if (!name || !value.trim()) return
        // the form clears once the value is on the item; a refusal leaves it as typed
        void onAdd({ field: name, value: value.trim(), unit: unit.trim(), provenance })
          .then(() => {
            setField('')
            setValue('')
            setUnit('')
          })
          .catch(() => undefined)
      }}
    >
      <h4>Add what you know</h4>
      <label>
        <span>Field</span>
        <input value={field} onChange={(e) => setField(e.target.value)} placeholder="color" />
      </label>
      <label>
        <span>Value</span>
        <input value={value} onChange={(e) => setValue(e.target.value)} placeholder="black" />
      </label>
      <label>
        <span>Unit</span>
        <input value={unit} onChange={(e) => setUnit(e.target.value)} placeholder="" />
      </label>
      <label>
        <span>Known from</span>
        <select value={provenance} onChange={(e) => setProvenance(e.target.value as Provenance)}>
          {PROVENANCES.filter((p) => p.value !== 'observed').map((p) => (
            <option key={p.value} value={p.value}>
              {p.label}
            </option>
          ))}
        </select>
      </label>
      <button type="submit" disabled={!name || !value.trim()}>
        Add field
      </button>
    </form>
  )
}

function AddComponent({ onAdd }: { onAdd: (spec: { name: string; condition: string }) => Promise<void> }) {
  const [name, setName] = useState('')
  const [condition, setCondition] = useState('')
  return (
    <form
      className="inline"
      onSubmit={(e: FormEvent) => {
        e.preventDefault()
        if (!name.trim()) return
        void onAdd({ name: name.trim(), condition: condition.trim() })
          .then(() => {
            setName('')
            setCondition('')
          })
          .catch(() => undefined)
      }}
    >
      <h4>Separate a part into its own item</h4>
      <label>
        <span>Part</span>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="power cable" />
      </label>
      <label>
        <span>Part condition</span>
        <input value={condition} onChange={(e) => setCondition(e.target.value)} placeholder="works" />
      </label>
      <button type="submit" disabled={!name.trim()}>
        Separate
      </button>
    </form>
  )
}
