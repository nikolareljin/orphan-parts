import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { api, type Item, type ItemEvent, type ItemSummary, type ProfileSummary, type Provenance } from '../lib/api'
import { fieldLabel, percent, printedDiffers, withUnit } from '../lib/format'
import { AVAILABILITIES, INTENTS, PROVENANCES, availabilityLabel, changedDetails, intentLabel, isConflict, mergeDetails, proposedCount, provenanceLabel, reviewLabel, whenText } from '../lib/inventory'
import Assess from './Assess'
import Decide from './Decide'
import GatedImage from './GatedImage'
import Listing from './Listing'
import Modal from './Modal'
import Measure from './Measure'
import { ItemSearch } from './SearchPlan'
import Picture from './Picture'
import SectionNav, { type SectionEntry } from './SectionNav'
import Value from './Value'

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
}: {
  refresh: number
  openId?: number | null
  onOpened?: () => void
  demo?: boolean
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
        <p className="muted">No items yet. Read a label and save it to add one.</p>
      )}
      {items !== null && items.length > 0 && (
        <table className="items" aria-label="Items">
          <thead>
            <tr>
              <th scope="col">Item</th>
              <th scope="col">Fields</th>
              <th scope="col">Plan</th>
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
                <td>{intentLabel(s.intent)}</td>
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

function ItemPanel({ id, demo, onChanged, onClosed }: { id: number; demo: boolean; onChanged: () => void; onClosed: () => void }) {
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
  const readOnly = demo || item.redacted === true
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
        <h4>Facts</h4>
        <ItemPhotos id={item.id} />
        <div className="row">
          <label>
            <span>Plan</span>
            <select
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
          <p className="muted">No fields yet.</p>
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
                      {a.review === 'proposed' && (
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

        <AddField onAdd={(spec) => apply(() => api.items.addField(item.id, spec))} />

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
            <p className="meta">Shown as in the public demo; sign in with the code to edit the details.</p>
          ) : (
            <button type="submit" disabled={!detailsChanged}>
              Save details
            </button>
          )}
        </form>

        <AddComponent
          onAdd={(spec) =>
            apply(async () => {
              // the part is its own record; this page stays on the whole and shows what left
              await api.items.addComponent(item.id, spec)
              return api.items.get(item.id)
            })
          }
        />
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
        />
      </div>

      <div className="item-section" data-section="value">
        <Value item={item} refresh={guided} onGuided={() => setGuided((n) => n + 1)} />
      </div>

      <div className="item-section" data-section="sell">
        <Listing item={item} onChanged={() => attempt(() => api.items.get(item.id))} />
      </div>

      <div className="item-section" data-section="fit">
        <Measure item={item} onMeasured={() => attempt(() => api.items.get(item.id))} />
        <Assess item={item} />
        {!demo && <ItemSearch item={item} />}
      </div>

      {/* the wrapper stays empty, and hidden, when there is no picture to show */}
      <div className="item-section" data-section="picture">
        <Picture item={item} demo={demo} />
      </div>

      <div className="item-footer">
        <label className="check">
          <input
            type="checkbox"
            checked={item.public}
            onChange={(e) => attempt(() => api.items.setPublic(item.id, e.target.checked))}
          />
          <span>
            Show in the public demo{' '}
            <small className="muted">Visitors without the access code can open this item, its photos and drawings. Location and notes stay private.</small>
          </span>
        </label>
        <span className="item-actions">
          <button type="button" className="link" onClick={() => void showEvents()}>
            History
          </button>
          {confirmDelete ? (
            <button type="button" className="danger" onClick={() => void remove()}>
              Yes, delete item #{item.id}
            </button>
          ) : (
            <button type="button" className="danger quiet" onClick={() => setConfirmDelete(true)}>
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
// One click makes a photo large, another shrinks it.
function ItemPhotos({ id }: { id: number }) {
  const [count, setCount] = useState<number | null>(null)
  const [big, setBig] = useState<number | null>(null)

  useEffect(() => {
    let cancelled = false
    setCount(null)
    setBig(null)
    api.items
      .photos(id)
      .then((p) => {
        if (!cancelled) setCount(p.count)
      })
      .catch(() => {
        if (!cancelled) setCount(-1) // not known: nothing is said either way
      })
    return () => {
      cancelled = true
    }
  }, [id])

  if (count === null || count < 0) return null
  if (count === 0) return <p className="muted no-photos">No photos saved with this item.</p>
  return (
    <div className="item-photos" aria-label="Photos">
      {Array.from({ length: count }, (_, i) => i + 1).map((n) => (
        <button
          key={n}
          type="button"
          className={`link photo${big === n ? ' open' : ''}`}
          title={big === n ? 'Shrink' : 'Enlarge'}
          onClick={() => setBig(big === n ? null : n)}
        >
          <GatedImage src={api.items.photoUrl(id, n)} alt={`Item photo ${n}`} loading="lazy" />
        </button>
      ))}
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
