import { useEffect, useState, type ChangeEvent, type FormEvent } from 'react'
import { api, type Draft, type DraftMode, type Item } from '../lib/api'
import { usd } from '../lib/format'
import { MODES, draftText, groupLabel, remaining, stepsByGroup } from '../lib/listing'
import SignInLine from './SignInLine'

function message(err: unknown): string {
  return err instanceof Error ? err.message : String(err)
}

// From a private record to a listing someone else will read: the draft, and the steps before.
export default function Listing({ item, onChanged, demo = false }: { item: Item; onChanged: () => void; demo?: boolean }) {
  const [mode, setMode] = useState<DraftMode>(item.intent === 'give' ? 'give' : 'sell')
  const [holdsData, setHoldsData] = useState(false)
  const [pickup, setPickup] = useState('')
  const [price, setPrice] = useState('')
  const [draft, setDraft] = useState<Draft | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [copied, setCopied] = useState(false)
  const [note, setNote] = useState('')
  const [noteCut, setNoteCut] = useState(false)

  // a decision on the item (Sell, Give away) picks the mode; any other intent leaves the radio
  // where it is, and the radio still changes it
  useEffect(() => {
    if (item.intent === 'sell' || item.intent === 'give') setMode(item.intent)
  }, [item.intent])

  useEffect(() => {
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
    return () => {
      cancelled = true
    }
    // the item's version too: an edit after drafting is what makes a draft stale
  }, [item.id, item.version])

  async function write(event: FormEvent) {
    event.preventDefault()
    if (busy) return
    setBusy(true)
    setError('')
    setCopied(false)
    try {
      setDraft(await api.drafts.write(item.id, { mode, holds_data: holdsData, pickup, asking_price: mode === 'sell' ? price : '' }))
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

  async function copy() {
    if (!draft) return
    try {
      await navigator.clipboard.writeText(draftText(draft))
      setCopied(true)
    } catch (err: unknown) {
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

  return (
    <section className="listing" aria-label="Prepare to sell or give away">
      <h4 tabIndex={-1}>Prepare to sell or give away</h4>
      {demo ? (
        // the demo set carries no voice note to stand in for one of the visitor's own
        <SignInLine what="Voice note (WAV)" />
      ) : (
        <div className="row">
          <label>
            <span>Voice note (WAV)</span>
            <input type="file" accept="audio/wav,.wav" onChange={(e) => void onVoice(e)} disabled={busy} />
          </label>
        </div>
      )}
      {note && (
        <p className="hint">
          Transcribed and saved as condition notes: <q>{note}</q>
          {noteCut && ' (too long; only the first part was saved)'}
        </p>
      )}
      <form onSubmit={(e) => void write(e)}>
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
          <label className="check">
            <input type="checkbox" checked={holdsData} onChange={(e) => setHoldsData(e.target.checked)} />
            <span>Holds personal data (adds steps to wipe it)</span>
          </label>
        </div>
        <div className="row">
          <label>
            <span>Pickup</span>
            <input value={pickup} onChange={(e) => setPickup(e.target.value)} placeholder="area, times, how to hand it over" />
          </label>
          {mode === 'sell' && (
            <label>
              <span>Asking price</span>
              <input value={price} onChange={(e) => setPrice(e.target.value)} placeholder="your price" />
            </label>
          )}
          <button type="submit" disabled={busy}>
            {busy ? 'Working…' : 'Write the draft'}
          </button>
        </div>
      </form>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {draft && (
        <DraftView draft={draft} copied={copied} onCopy={() => void copy()} onTick={(k, d) => void tick(k, d)} />
      )}
    </section>
  )
}

function DraftView({
  draft,
  copied,
  onCopy,
  onTick,
}: {
  draft: Draft
  copied: boolean
  onCopy: () => void
  onTick: (key: string, done: boolean) => void
}) {
  const left = remaining(draft.checklist)
  return (
    <div className="draft" role="status" aria-label={`Draft ${draft.version}`}>
      <p className="meta">
        {draft.mode === 'sell' ? 'For sale' : 'Free'} · draft {draft.version} · {draft.model} · {usd(draft.cost_usd)}
        {draft.from_fixture && <span className="badge">recorded answer</span>}
        {draft.stale && <span className="badge">item changed since</span>}
      </p>
      <h5>{draft.title}</h5>
      <textarea className="draft-text" readOnly aria-label="Draft text" value={draftText(draft)} />
      {draft.facts.length > 0 && (
        <ul className="facts" aria-label="Facts">
          {draft.facts.map((f, i) => (
            <li key={`${i}:${f.field}`}>
              {f.text} <small>from {f.field.replace(/_/g, ' ')}</small>
            </li>
          ))}
        </ul>
      )}
      {draft.uses.length > 0 && (
        <p className="meta">Could be useful for: {draft.uses.join('; ')}.</p>
      )}
      {draft.warnings.length > 0 && (
        <ul className="warnings" aria-label="Before posting">
          {draft.warnings.map((w, i) => (
            <li key={`${i}:${w.slice(0, 24)}`}>{w}</li>
          ))}
        </ul>
      )}
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
      <div className="row">
        <button type="button" onClick={onCopy}>
          {copied ? 'Copied' : 'Copy the draft'}
        </button>
        <a href={draft.handoff_url} target="_blank" rel="noopener noreferrer">
          Open Marketplace
        </a>
        <span className="muted">Paste it into the new-listing form on Marketplace. Nothing is posted from here.</span>
      </div>
    </div>
  )
}
