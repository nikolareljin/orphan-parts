import { useEffect, useId, useState, type ChangeEvent, type FormEvent } from 'react'
import { api, mediaUrl, type Draft, type DraftMode, type Included, type Item, type MarketplaceData, type MarketplaceStatus, type SellDetails } from '../lib/api'
import { usd } from '../lib/format'
import {
  DATA_STATES,
  HANDOVERS,
  HARD_LIMIT,
  INCLUDED,
  MODES,
  categoryText,
  copyFields,
  copyText,
  detailsToSave,
  dollars,
  emptyDetails,
  groupLabel,
  handoffSteps,
  parsePrice,
  priceInput,
  priceLabel,
  listedLabel,
  remaining,
  sameDetails,
  stepsByGroup,
  today,
  type CopyKey,
} from '../lib/listing'
import GatedImage from './GatedImage'
import SignInLine from './SignInLine'

function message(err: unknown): string {
  return err instanceof Error ? err.message : String(err)
}

// From a private record to a Facebook Marketplace listing the owner posts: what the owner adds,
// the draft in Marketplace's shape, the fields to paste, and what happened after.
// samplesOnly: no file input until uploads are known to be open (the visitor, or access not known yet)
export default function Listing({
  item,
  readOnly = false,
  samplesOnly = readOnly,
  onChanged,
}: {
  item: Item
  readOnly?: boolean
  samplesOnly?: boolean
  onChanged: () => void
}) {
  const [mode, setMode] = useState<DraftMode>(item.intent === 'give' ? 'give' : 'sell')
  const [details, setDetails] = useState<SellDetails>(emptyDetails)
  const [saved, setSaved] = useState<number | null>(null)
  // the details as last saved, so a draft written from unchanged details saves nothing new
  const [stored, setStored] = useState<SellDetails | null>(null)
  // whether the owner's saved details were read: until then the form is blank, and saving it
  // would write the blanks over them
  const [loaded, setLoaded] = useState(false)
  const [asking, setAsking] = useState('')
  const [lowest, setLowest] = useState('')
  const [draft, setDraft] = useState<Draft | null>(null)
  const [status, setStatus] = useState<MarketplaceStatus | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [note, setNote] = useState('')
  const [noteCut, setNoteCut] = useState(false)
  const dataId = useId()

  // a decision on the item (Sell, Give away) picks the mode; any other intent leaves the radio
  // where it is, and the radio still changes it
  useEffect(() => {
    if (item.intent === 'sell' || item.intent === 'give') setMode(item.intent)
  }, [item.intent])

  useEffect(() => {
    if (readOnly) return
    let cancelled = false
    api.marketplace
      .details(item.id)
      .then((record) => {
        if (cancelled) return
        setLoaded(true)
        if (record === null) return
        setDetails(record.details)
        setStored(record.details)
        setSaved(record.version)
        setAsking(priceInput(record.details.asking_price))
        setLowest(priceInput(record.details.lowest_price))
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(`the saved listing details could not be read (${message(err)}); nothing is saved until they are`)
      })
    return () => {
      cancelled = true
    }
  }, [item.id, readOnly])

  useEffect(() => {
    if (readOnly) return
    let cancelled = false
    api.drafts
      .list(item.id)
      .then((list) => {
        if (cancelled) return
        // a draft written meanwhile is newer than anything this list holds
        const latest = list.length > 0 ? list[list.length - 1] : null
        setDraft((current) => (latest === null || (current && current.id > latest.id) ? current : latest))
      })
      .catch(() => {
        if (!cancelled) setDraft(null)
      })
    api.marketplace
      .status(item.id)
      .then((s) => {
        if (!cancelled) setStatus(s)
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
    // the item's version too: an edit after drafting is what makes a draft stale
  }, [item.id, item.version, readOnly])

  function set<K extends keyof SellDetails>(key: K, value: SellDetails[K]) {
    setDetails((d) => ({ ...d, [key]: value }))
  }

  function toggleIncluded(value: Included, on: boolean) {
    setDetails((d) => ({ ...d, included: on ? [...d.included, value] : d.included.filter((v) => v !== value) }))
  }

  // the prices as typed, checked; a give-away keeps the saved ones
  function withPrices(): SellDetails | null {
    const next = detailsToSave(details, mode, asking, lowest)
    if ('error' in next) {
      setError(next.error)
      return null
    }
    return next.details
  }

  // saved as a new version; with onlyChanged, details the same as the saved ones are kept as
  // they are (a draft written again adds no "listing details saved" line to the history)
  async function saveDetails(onlyChanged = false): Promise<boolean> {
    if (readOnly || !loaded) return false
    const next = withPrices()
    if (next === null) return false
    if (onlyChanged && stored !== null && sameDetails(next, stored)) return true
    const record = await api.marketplace.saveDetails(item.id, next)
    setDetails(record.details)
    setStored(record.details)
    setSaved(record.version)
    return true
  }

  async function onSave() {
    if (busy) return
    setBusy(true)
    setError('')
    try {
      await saveDetails()
    } catch (err: unknown) {
      setError(message(err))
    } finally {
      setBusy(false)
    }
  }

  // the details are saved first, so the draft is written from what is on the form
  async function write(event: FormEvent) {
    event.preventDefault()
    if (busy) return
    setBusy(true)
    setError('')
    try {
      if (!(await saveDetails(true))) return
      setDraft(await api.drafts.write(item.id, { mode, holds_data: details.data !== 'none', pickup: '', asking_price: '' }))
      onChanged()
    } catch (err: unknown) {
      setError(message(err))
    } finally {
      setBusy(false)
    }
  }

  async function tick(key: string, done: boolean) {
    if (!draft) return
    // shown as ticked at once; the stored state comes back and replaces it
    const before = draft
    setDraft({ ...draft, checklist: draft.checklist.map((s) => (s.key === key ? { ...s, done } : s)) })
    try {
      setDraft(await api.drafts.setStep(draft.id, key, done))
    } catch (err: unknown) {
      setDraft(before)
      setError(message(err))
    }
  }

  async function onVoice(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    if (!file) return
    setBusy(true)
    setError('')
    try {
      const heard = await api.voice(item.id, file)
      setNote(heard.transcript)
      setNoteCut(heard.cut)
      onChanged()
    } catch (err: unknown) {
      setError(message(err))
    } finally {
      setBusy(false)
      event.target.value = ''
    }
  }

  async function record(run: () => Promise<MarketplaceStatus>) {
    setError('')
    try {
      setStatus(await run())
      onChanged()
    } catch (err: unknown) {
      setError(message(err))
    }
  }

  // the demo visitor, or an item served as the visitor sees it: the listing details, drafts and
  // outcomes are the owner's and are never read or written from here
  if (readOnly)
    return (
      <section className="listing" aria-label="Prepare to sell or give away">
        <h4 tabIndex={-1}>Prepare to sell or give away</h4>
        <p className="hint limit">{HARD_LIMIT}</p>
        <p className="meta">Sign in with the code to prepare a listing.</p>
        {/* the demo set carries no voice note to stand in for one of the visitor's own */}
        <SignInLine what="Voice note (WAV)" />
      </section>
    )

  return (
    <section className="listing" aria-label="Prepare to sell or give away">
      <h4 tabIndex={-1}>Prepare to sell or give away</h4>
      <p className="hint limit">{HARD_LIMIT}</p>
      <form className="tell" aria-label="Listing details" onSubmit={(e) => void write(e)}>
        <h5>Listing details</h5>
        <div className="row options">
          <fieldset className="choice">
            <legend>Listing type</legend>
            {MODES.map((m) => (
              <label key={m.value} className="check">
                <input type="radio" name="mode" checked={mode === m.value} onChange={() => setMode(m.value)} />
                <span>{m.label}</span>
              </label>
            ))}
          </fieldset>
          {mode === 'sell' && (
            <fieldset className="choice">
              <legend>Handover</legend>
              {HANDOVERS.map((h) => (
                <label key={h.value} className="check">
                  <input type="radio" name="handover" checked={details.handover === h.value} onChange={() => set('handover', h.value)} />
                  <span>{h.label}</span>
                </label>
              ))}
            </fieldset>
          )}
        </div>
        <div className="row">
          <label>
            <span>Condition in your words</span>
            <textarea rows={2} value={details.condition_words} onChange={(e) => set('condition_words', e.target.value)} placeholder="works, light scratches on the stand" />
          </label>
          <label>
            <span>Known faults or cosmetic issues</span>
            <textarea rows={2} value={details.faults} onChange={(e) => set('faults', e.target.value)} placeholder="one stuck pixel; a scuff on the bezel" />
          </label>
        </div>
        <fieldset className="choice included">
          <legend>Included</legend>
          {INCLUDED.map((i) => (
            <label key={i.value} className="check">
              <input type="checkbox" checked={details.included.includes(i.value)} onChange={(e) => toggleIncluded(i.value, e.target.checked)} />
              <span>{i.label}</span>
            </label>
          ))}
        </fieldset>
        <div className="row">
          <label>
            <span>Other included</span>
            <input value={details.included_other} onChange={(e) => set('included_other', e.target.value)} placeholder="VGA cable, DVI cable" />
          </label>
          <label>
            <span>Not tested</span>
            <input value={details.untested} onChange={(e) => set('untested', e.target.value)} placeholder="the DVI input" />
          </label>
          <label>
            <span id={`${dataId}-label`}>Personal data on it</span>
            <select value={details.data} aria-labelledby={`${dataId}-label`} aria-describedby={`${dataId}-hint`} onChange={(e) => set('data', e.target.value as SellDetails['data'])}>
              {DATA_STATES.map((d) => (
                <option key={d.value} value={d.value}>
                  {d.label}
                </option>
              ))}
            </select>
            <small id={`${dataId}-hint`} className="muted">
              Holds personal data (adds steps to wipe it)
            </small>
          </label>
          <label>
            <span>Area</span>
            <input value={details.area} onChange={(e) => set('area', e.target.value)} placeholder="city, ZIP or neighborhood" />
          </label>
          <label>
            <span>Availability</span>
            <input value={details.availability} onChange={(e) => set('availability', e.target.value)} placeholder="weekday evenings" />
          </label>
          {mode === 'sell' && (
            <>
              <label>
                <span>Asking price (USD)</span>
                <input inputMode="decimal" value={asking} onChange={(e) => setAsking(e.target.value)} placeholder="leave empty to use price guidance" />
              </label>
              <label>
                <span>Lowest you would take (private)</span>
                <input inputMode="decimal" value={lowest} onChange={(e) => setLowest(e.target.value)} placeholder="not shown in the listing" />
              </label>
              <label>
                <span>Your reason (private)</span>
                <input value={details.reason} onChange={(e) => set('reason', e.target.value)} placeholder="not shown in the listing" />
              </label>
            </>
          )}
          {samplesOnly ? (
            <SignInLine what="Voice note (WAV)" />
          ) : (
            <label>
              <span>Voice note (WAV)</span>
              <input type="file" accept="audio/wav,.wav" onChange={(e) => void onVoice(e)} disabled={busy} />
            </label>
          )}
        </div>
        {note && (
          <p className="hint">
            Transcribed and saved as condition notes: <q>{note}</q>
            {noteCut && ' (too long; only the first part was saved)'}
          </p>
        )}
        <p className="hint">Never a street address, a phone number or an email: buyers write through Marketplace.</p>
        <div className="row actions">
          <button type="submit" disabled={busy || !loaded}>
            {busy ? 'Working…' : 'Write the draft'}
          </button>
          <button type="button" disabled={busy || !loaded} onClick={() => void onSave()}>
            Save details
          </button>
          {saved !== null && <span className="muted">Details saved (version {saved})</span>}
        </div>
      </form>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {draft && (
        <Handoff
          key={draft.id}
          draft={draft}
          itemId={item.id}
          detailsChanged={saved !== null && draft.details_version !== saved}
          status={status}
          onTick={(k, d) => void tick(k, d)}
          onRecord={record}
          onError={setError}
        />
      )}
    </section>
  )
}

function Handoff({
  draft,
  itemId,
  detailsChanged,
  status,
  onTick,
  onRecord,
  onError,
}: {
  draft: Draft
  itemId: number
  detailsChanged: boolean
  status: MarketplaceStatus | null
  onTick: (key: string, done: boolean) => void
  onRecord: (run: () => Promise<MarketplaceStatus>) => Promise<void>
  onError: (text: string) => void
}) {
  const [copied, setCopied] = useState<CopyKey | null>(null)
  const [market, setMarket] = useState<MarketplaceData | null>(null)
  const [category, setCategory] = useState(draft.category)
  const [condition, setCondition] = useState(draft.condition)
  const left = remaining(draft.checklist)

  useEffect(() => {
    let cancelled = false
    api.marketplace
      .data()
      .then((d) => {
        if (!cancelled) setMarket(d)
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [])

  async function copy(key: CopyKey, text: string) {
    try {
      await copyText(text)
      setCopied(key)
    } catch (err: unknown) {
      onError(message(err))
    }
  }

  async function download() {
    const src = api.drafts.photosZipUrl(draft.id)
    try {
      // same origin the link carries the cookie; across origins the zip comes with the session
      const url = await mediaUrl(src)
      const a = document.createElement('a')
      a.href = url
      a.download = `item-${itemId}-photos.zip`
      document.body.appendChild(a)
      a.click()
      a.remove()
      if (url !== src) setTimeout(() => URL.revokeObjectURL(url), 10_000)
    } catch (err: unknown) {
      onError(message(err))
    }
  }

  function value(key: CopyKey, text: string) {
    if (key === 'description') return <textarea className="draft-text" readOnly aria-label="Draft text" value={text} />
    if (key === 'price') return <span className="value">{priceLabel(draft)}</span>
    if (key === 'category' && market)
      return (
        <select aria-label="Category" value={category} onChange={(e) => setCategory(e.target.value)}>
          {!category && <option value="">choose one</option>}
          {market.categories.map((c) => (
            <option key={c.path} value={c.path}>
              {categoryText(c.path)}
            </option>
          ))}
        </select>
      )
    if (key === 'condition' && market)
      return (
        <select aria-label="Condition" value={condition} onChange={(e) => setCondition(e.target.value)}>
          {!condition && <option value="">choose one</option>}
          {market.conditions.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
      )
    return <span className="value">{text || <span className="muted">not set</span>}</span>
  }

  return (
    <section className="draft handoff" aria-label="Marketplace handoff">
      <h5>Marketplace handoff</h5>
      <p className="meta" role="status">
        {draft.mode === 'sell' ? 'For sale' : 'Free'} · draft {draft.version} · {draft.model} · {usd(draft.cost_usd)}
        {draft.from_fixture && <span className="badge">recorded answer</span>}
        {draft.stale && <span className="badge">item changed since</span>}
        {detailsChanged && <span className="badge">details changed since this draft</span>}
      </p>
      {draft.warnings.length > 0 && (
        <ul className="warnings" aria-label="Before posting">
          {draft.warnings.map((w, i) => (
            <li key={`${i}:${w.slice(0, 24)}`}>{w}</li>
          ))}
        </ul>
      )}
      <p className="visually-hidden" role="status">
        {copied ? `${copyFields(draft).find((f) => f.key === copied)?.label ?? ''} copied` : ''}
      </p>
      <dl className="fields" aria-label="Fields to paste">
        {copyFields(draft, { category, condition }).map((f) => (
          <div key={f.key} className={`field ${f.key}`}>
            <dt>{f.label}</dt>
            <dd>
              {value(f.key, f.text)}
              {f.key === 'price' && draft.price_basis && <small className="muted">{draft.price_basis}</small>}
              <button type="button" className="copy" aria-label={`Copy ${f.label.toLowerCase()}`} disabled={!f.text} onClick={() => void copy(f.key, f.text)}>
                {copied === f.key ? 'Copied' : 'Copy'}
              </button>
            </dd>
          </div>
        ))}
      </dl>
      {draft.photos.length > 0 && (
        <ol className="photo-order" aria-label="Photo order">
          {draft.photos.map((p, i) => (
            <li key={p.photo}>
              <GatedImage src={api.items.photoUrl(itemId, p.photo)} alt={`Photo ${p.photo}`} loading="lazy" />
              <span>
                {i + 1}. Photo {p.photo}: {p.reason}
              </span>
            </li>
          ))}
        </ol>
      )}
      <div className="row actions">
        <a className="button" href={draft.handoff_url} target="_blank" rel="noopener noreferrer">
          Open Marketplace
        </a>
        {draft.photos.length > 0 && (
          <button type="button" className="secondary" onClick={() => void download()}>
            Download photos
          </button>
        )}
        <span className="muted">Paste it into the new-listing form on Marketplace. Nothing is posted from here.</span>
      </div>
      <h5>On Marketplace</h5>
      <ol className="handoff-steps">
        {handoffSteps(draft).map((s) => (
          <li key={s}>{s}</li>
        ))}
      </ol>
      {draft.facts.length > 0 && (
        <details className="facts-wrap">
          <summary>Where each line comes from</summary>
          <ul className="facts" aria-label="Facts">
            {draft.facts.map((f, i) => (
              <li key={`${i}:${f.field}`}>
                {f.text} <small>from {f.field.replace(/_/g, ' ')}</small>
              </li>
            ))}
          </ul>
        </details>
      )}
      {draft.uses.length > 0 && <p className="meta">Could be useful for: {draft.uses.join('; ')}.</p>}
      {stepsByGroup(draft.checklist).map(([group, steps]) => (
        <div key={group}>
          <h5>{groupLabel(group)}</h5>
          <ul className="steps">
            {steps.map((s) => (
              <li key={s.key}>
                <label className="check">
                  <input type="checkbox" checked={s.done} onChange={(e) => onTick(s.key, e.target.checked)} />
                  <span>
                    {s.label} {!s.required && <small>(optional)</small>}
                  </span>
                </label>
              </li>
            ))}
          </ul>
        </div>
      ))}
      <p className="meta">{draft.ready ? 'Every required step is done.' : `${left} required step(s) left.`}</p>
      <Outcomes draft={draft} itemId={itemId} status={status} onRecord={onRecord} />
    </section>
  )
}

function Outcomes({
  draft,
  itemId,
  status,
  onRecord,
}: {
  draft: Draft
  itemId: number
  status: MarketplaceStatus | null
  onRecord: (run: () => Promise<MarketplaceStatus>) => Promise<void>
}) {
  const [on, setOn] = useState(today())
  const [price, setPrice] = useState(draft.price)
  const [url, setUrl] = useState('')
  // one outcome at a time: a second click while a sale is recorded would be refused as sold
  const [pending, setPending] = useState(false)
  const state = status?.state ?? ''
  const done = state === 'sold' || state === 'given'
  const amount = parsePrice(price)
  // a sale is listed at a price above 0, which Marketplace would show as free
  const canList = (state === '' || state === 'listed') && (draft.mode === 'give' || (amount !== null && amount > 0))

  async function run(call: () => Promise<MarketplaceStatus>) {
    if (pending) return
    setPending(true)
    try {
      await onRecord(call)
    } finally {
      setPending(false)
    }
  }

  return (
    <section className="outcomes" aria-label="After posting">
      <h5>After posting</h5>
      {status && status.events.length > 0 && (
        <ul className="events">
          {status.events.map((e) => (
            <li key={e.id}>
              {e.kind} on {e.on}
              {e.price !== null && e.kind !== 'given' && ` at ${dollars(e.price)}`}
              {e.url && (
                <>
                  {' · '}
                  <a href={e.url} target="_blank" rel="noopener noreferrer">
                    the listing
                  </a>
                </>
              )}
            </li>
          ))}
        </ul>
      )}
      {!done && (
        <div className="row">
          <label>
            <span>Date</span>
            <input type="date" value={on} max={today()} onChange={(e) => setOn(e.target.value)} />
          </label>
          {draft.mode === 'sell' && (
            <label>
              <span>Price (USD)</span>
              <input inputMode="decimal" value={price} onChange={(e) => setPrice(e.target.value)} />
            </label>
          )}
          <label>
            <span>Listing link (optional)</span>
            <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://www.facebook.com/marketplace/item/…" />
          </label>
        </div>
      )}
      {!done && (
        <div className="row actions">
          <button
            type="button"
            disabled={pending || !canList}
            onClick={() => void run(() => api.marketplace.listed(itemId, { on, price: draft.mode === 'give' ? 0 : (amount ?? 0), url: url.trim() }))}
          >
            {listedLabel(state, draft.mode, amount)}
          </button>
          {draft.mode === 'sell' ? (
            <button
              type="button"
              className="secondary"
              disabled={pending || !amount}
              onClick={() => void run(() => api.marketplace.sold(itemId, { on, price: amount ?? 0 }))}
            >
              Mark as sold
            </button>
          ) : (
            <button type="button" className="secondary" disabled={pending} onClick={() => void run(() => api.marketplace.given(itemId, { on }))}>
              Mark as given
            </button>
          )}
          {draft.mode === 'sell' && <span className="muted">A sale is also recorded for price guidance.</span>}
        </div>
      )}
    </section>
  )
}
