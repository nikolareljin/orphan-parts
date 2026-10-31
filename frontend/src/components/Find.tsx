import { useCallback, useEffect, useState, type ChangeEvent, type FormEvent } from 'react'
import { api, type Candidate, type ItemSummary, type ProfileRule, type ProfileSummary, type Search, type SourceKind } from '../lib/api'
import { usd } from '../lib/format'
import { SOURCES, candidateRequest, seenText, sourceLabel, stateLabel, stateTone, statusLabel } from '../lib/find'
import { inputLabel, ruleHint } from '../lib/match'
import { Result } from './Assess'
import Modal from './Modal'

function message(err: unknown): string {
  return err instanceof Error ? err.message : String(err)
}

// Find the one that fits: a search the owner runs on Marketplace, and the listings brought back.
export default function Find() {
  const [searches, setSearches] = useState<Search[]>([])
  const [openId, setOpenId] = useState<number | null>(null)
  const [error, setError] = useState('')

  const load = useCallback(() => {
    api.find
      .searches()
      .then(setSearches)
      .catch((err: unknown) => setError(message(err)))
  }, [])

  useEffect(() => {
    load()
  }, [load])

  return (
    <div className="find">
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <NewSearch
        onCreated={(s) => {
          load()
          setOpenId(s.id)
        }}
      />
      {searches.length === 0 ? (
        <p className="muted">No searches yet. Describe the part you need above; you run the search on Marketplace yourself.</p>
      ) : (
        <table className="evidence" aria-label="Searches">
          <thead>
            <tr>
              <th scope="col">Looking for</th>
              <th scope="col">Profile</th>
              <th scope="col">Status</th>
              <th scope="col">Candidates</th>
              <th scope="col"></th>
            </tr>
          </thead>
          <tbody>
            {searches.map((s) => (
              <tr key={s.id}>
                <td>{s.title}</td>
                <td>{s.profile}</td>
                <td>{statusLabel(s.status)}</td>
                <td>{s.candidates}</td>
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
        <Modal title={`Search #${openId}`} onClose={() => setOpenId(null)}>
          <SearchPanel key={openId} id={openId} onChanged={load} onClosed={() => setOpenId(null)} />
        </Modal>
      )}
    </div>
  )
}

function NewSearch({ onCreated }: { onCreated: (s: Search) => void }) {
  const [items, setItems] = useState<ItemSummary[]>([])
  const [profiles, setProfiles] = useState<ProfileSummary[]>([])
  const [needItemId, setNeedItemId] = useState<number | null>(null)
  const [profile, setProfile] = useState('')
  const [rules, setRules] = useState<ProfileRule[]>([])
  const [spec, setSpec] = useState<Record<string, string>>({})
  const [title, setTitle] = useState('')
  const [maxPrice, setMaxPrice] = useState('')
  const [currency, setCurrency] = useState('USD')
  const [radius, setRadius] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    Promise.all([api.items.list(), api.profiles.list()])
      .then(([list, profs]) => {
        if (cancelled) return
        setItems(list.filter((i) => i.profile))
        setProfiles(profs)
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    setSpec({})
    if (needItemId !== null || !profile) {
      setRules([])
      return
    }
    api.profiles
      .rules(profile)
      .then((list) => {
        if (!cancelled) setRules(list)
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [needItemId, profile])

  async function create(event: FormEvent) {
    event.preventDefault()
    if (busy) return
    setBusy(true)
    setError('')
    try {
      const kept: Record<string, string> = {}
      for (const [k, v] of Object.entries(spec)) if (v.trim()) kept[k] = v.trim()
      const created = await api.find.create({
        need_item_id: needItemId,
        profile: needItemId === null ? profile : '',
        title,
        spec: kept,
        max_price: maxPrice.trim() ? Number(maxPrice) : null,
        currency,
        radius_km: radius.trim() ? Number(radius) : null,
      })
      setTitle('')
      onCreated(created)
    } catch (err: unknown) {
      setError(message(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="new-search" onSubmit={(e) => void create(e)} aria-label="New search">
      <h3>I need one that fits</h3>
      <div className="row">
        <label>
          <span>Needed by</span>
          <select
            value={needItemId ?? ''}
            onChange={(e) => {
              setNeedItemId(e.target.value === '' ? null : Number(e.target.value))
            }}
          >
            <option value="">Values I type below</option>
            {items.map((i) => (
              <option key={i.id} value={i.id}>
                #{i.id} {i.name} ({i.profile})
              </option>
            ))}
          </select>
        </label>
        {needItemId === null && (
          <label>
            <span>Profile</span>
            <select value={profile} onChange={(e) => setProfile(e.target.value)}>
              <option value="">pick one</option>
              {profiles.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.label}
                </option>
              ))}
            </select>
          </label>
        )}
        <label>
          <span>Looking for</span>
          <input value={title} maxLength={200} placeholder="65 W laptop adapter, 19.5 V" onChange={(e) => setTitle(e.target.value)} />
        </label>
      </div>
      {needItemId === null && rules.length > 0 && (
        <div className="needed">
          {rules.map((rule) => (
            <label key={rule.key} title={ruleHint(rule)}>
              <span>
                {inputLabel(rule)} <small className="muted">{rule.hard ? 'hard' : 'soft'}</small>
              </span>
              <input value={spec[rule.key] ?? ''} onChange={(e) => setSpec({ ...spec, [rule.key]: e.target.value })} />
            </label>
          ))}
        </div>
      )}
      <div className="row">
        <label>
          <span>Max price</span>
          <input value={maxPrice} inputMode="decimal" onChange={(e) => setMaxPrice(e.target.value)} />
        </label>
        <label>
          <span>Currency</span>
          <input value={currency} maxLength={3} onChange={(e) => setCurrency(e.target.value.toUpperCase())} />
        </label>
        <label>
          <span>Radius (km)</span>
          <input value={radius} inputMode="numeric" onChange={(e) => setRadius(e.target.value)} />
        </label>
        <button type="submit" disabled={busy || !title.trim() || (needItemId === null && !profile)}>
          {busy ? 'Working…' : 'Start the search'}
        </button>
      </div>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </form>
  )
}

function SearchPanel({ id, onChanged, onClosed }: { id: number; onChanged: () => void; onClosed: () => void }) {
  const [search, setSearch] = useState<Search | null>(null)
  const [candidates, setCandidates] = useState<Candidate[]>([])
  const [rules, setRules] = useState<ProfileRule[]>([])
  const [openCandidate, setOpenCandidate] = useState<number | null>(null)
  const [error, setError] = useState('')

  const load = useCallback(() => {
    Promise.all([api.find.get(id), api.find.candidates(id)])
      .then(([s, list]) => {
        setSearch(s)
        setCandidates(list)
      })
      .catch((err: unknown) => setError(message(err)))
  }, [id])

  useEffect(() => {
    load()
  }, [load])

  const profile = search?.profile ?? ''
  useEffect(() => {
    if (!profile) return
    let cancelled = false
    api.profiles
      .rules(profile)
      .then((list) => {
        if (!cancelled) setRules(list)
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
    // the profile, not the search object: a reload of the search is not a change of rules
  }, [profile])

  async function setStatus(status: Search['status']) {
    try {
      setSearch(await api.find.patch(id, { status }))
      onChanged()
    } catch (err: unknown) {
      setError(message(err))
    }
  }

  if (!search) return <p className="muted">Loading…</p>

  return (
    <article className="search-panel" aria-label={`Search ${search.title}`}>
      <div className="row">
        <h3>{search.title}</h3>
        <span className="badge">{statusLabel(search.status)}</span>
        <span className="muted">{search.profile} rules</span>
        <button type="button" className="link" onClick={onClosed}>
          Close panel
        </button>
      </div>
      <p className="meta">
        <a href={search.handoff_url} target="_blank" rel="noopener noreferrer">
          Search Marketplace
        </a>{' '}
        <span className="muted">opens the search in a new tab for you to run; nothing is fetched or posted from here. Then bring a listing back below.</span>
        {search.max_price !== null && ` · top price ${search.max_price} ${search.currency}`}
        {search.radius_km !== null && ` · within ${search.radius_km} km`}
      </p>
      {Object.keys(search.spec).length > 0 && (
        <p className="meta" aria-label="Needed values">
          Needs:{' '}
          {Object.entries(search.spec)
            .map(([k, v]) => `${k.replace(/_/g, ' ')} ${v}`)
            .join(', ')}
        </p>
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {search.status === 'closed' ? (
        <p className="muted">This search is closed; reopen it to bring a listing back.</p>
      ) : (
        <AddCandidate
          searchId={id}
          rules={rules}
          onAdded={(c) => {
            load()
            onChanged()
            setOpenCandidate(c.id)
          }}
        />
      )}
      {candidates.length > 0 && (
        <table className="evidence candidates" aria-label="Candidates">
          <thead>
            <tr>
              <th scope="col">Listing</th>
              <th scope="col">Status</th>
              <th scope="col">Price</th>
              <th scope="col">Seen</th>
              <th scope="col">Source</th>
              <th scope="col"></th>
            </tr>
          </thead>
          <tbody>
            {candidates.map((c) => (
              <tr key={c.id}>
                <td>{c.title || `candidate ${c.id}`}</td>
                <td>
                  <span className={`badge state ${stateTone(c.state)}`}>{stateLabel(c.state)}</span>
                </td>
                <td>{c.asking_price ? `${c.asking_price} ${c.currency}` : '—'}</td>
                <td>{seenText(c)}</td>
                <td>{sourceLabel(c.source_kind)}</td>
                <td>
                  <button type="button" className="link" onClick={() => setOpenCandidate(c.id)}>
                    Open
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {openCandidate !== null && (
        <CandidatePanel
          key={openCandidate}
          id={openCandidate}
          onChanged={() => {
            load()
            onChanged()
          }}
        />
      )}
      <div className="row">
        {search.status !== 'found' && (
          <button type="button" onClick={() => void setStatus('found')}>
            Mark found
          </button>
        )}
        {search.status !== 'closed' && (
          <button type="button" onClick={() => void setStatus('closed')}>
            Close search
          </button>
        )}
        {search.status !== 'open' && (
          <button type="button" onClick={() => void setStatus('open')}>
            Reopen
          </button>
        )}
      </div>
    </article>
  )
}

function AddCandidate({ searchId, rules, onAdded }: { searchId: number; rules: ProfileRule[]; onAdded: (c: Candidate) => void }) {
  const [source, setSource] = useState<SourceKind>('text')
  const [text, setText] = useState('')
  const [screenshot, setScreenshot] = useState<File | null>(null)
  const [values, setValues] = useState<Record<string, string>>({})
  const [observedOn, setObservedOn] = useState('')
  const [askingPrice, setAskingPrice] = useState('')
  const [currency, setCurrency] = useState('USD')
  const [location, setLocation] = useState('')
  const [url, setUrl] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function add(event: FormEvent) {
    event.preventDefault()
    if (busy) return
    setBusy(true)
    setError('')
    try {
      const request = candidateRequest({ source, text, values, observedOn, askingPrice, currency, location, url })
      const created = await api.find.addCandidate(searchId, request, source === 'screenshot' ? screenshot : null)
      setText('')
      setScreenshot(null)
      setValues({})
      setUrl('')
      onAdded(created)
    } catch (err: unknown) {
      setError(message(err))
    } finally {
      setBusy(false)
    }
  }

  function onFile(event: ChangeEvent<HTMLInputElement>) {
    setScreenshot(event.target.files?.[0] ?? null)
  }

  const ready = source === 'text' ? text.trim().length > 0 : source === 'screenshot' ? screenshot !== null : Object.values(values).some((v) => v.trim())

  return (
    <form className="add-candidate" onSubmit={(e) => void add(e)} aria-label="Bring a listing back">
      <h4>Bring a listing back</h4>
      <fieldset className="kind">
        <legend>Add from</legend>
        {SOURCES.map((s) => (
          <label key={s.value}>
            <input type="radio" name="source" checked={source === s.value} onChange={() => setSource(s.value)} />
            <span>{s.label}</span>
          </label>
        ))}
      </fieldset>
      {source === 'text' && (
        <label className="wide">
          <span>Listing text</span>
          <textarea value={text} rows={4} maxLength={8000} placeholder="paste the listing text" onChange={(e) => setText(e.target.value)} />
        </label>
      )}
      {source === 'screenshot' && (
        <label>
          <span>Screenshot</span>
          <input type="file" accept="image/*" onChange={onFile} />
        </label>
      )}
      {source === 'manual' && rules.length > 0 && (
        <div className="needed">
          {rules.map((rule) => (
            <label key={rule.key} title={ruleHint(rule)}>
              <span>{inputLabel(rule)}</span>
              <input value={values[rule.key] ?? ''} onChange={(e) => setValues({ ...values, [rule.key]: e.target.value })} />
            </label>
          ))}
        </div>
      )}
      <div className="row">
        <label>
          <span>Seen on</span>
          <input type="date" value={observedOn} onChange={(e) => setObservedOn(e.target.value)} />
        </label>
        <label>
          <span>Asking price</span>
          <input value={askingPrice} maxLength={40} onChange={(e) => setAskingPrice(e.target.value)} />
        </label>
        <label>
          <span>Currency</span>
          <input value={currency} maxLength={3} onChange={(e) => setCurrency(e.target.value.toUpperCase())} />
        </label>
        <label>
          <span>Where</span>
          <input value={location} maxLength={120} onChange={(e) => setLocation(e.target.value)} />
        </label>
        <label>
          <span>Link</span>
          <input value={url} maxLength={500} placeholder="saved as is, never opened" onChange={(e) => setUrl(e.target.value)} />
        </label>
        <button type="submit" disabled={busy || !ready || currency.length !== 3}>
          {busy ? 'Working…' : 'Check fit'}
        </button>
      </div>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </form>
  )
}

function CandidatePanel({ id, onChanged }: { id: number; onChanged: () => void }) {
  const [candidate, setCandidate] = useState<Candidate | null>(null)
  const [note, setNote] = useState<{ subject: string; message: string } | null>(null)
  const [copied, setCopied] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    setNote(null)
    api.find
      .candidate(id)
      .then((c) => {
        if (!cancelled) setCandidate(c)
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(message(err))
      })
    return () => {
      cancelled = true
    }
  }, [id])

  async function act(action: () => Promise<Candidate>) {
    try {
      setCandidate(await action())
      setNote(null)
      onChanged()
    } catch (err: unknown) {
      setError(message(err))
    }
  }

  async function askSeller() {
    try {
      const q = await api.find.questions(id)
      setNote({ subject: q.subject, message: q.message })
      setCopied(false)
    } catch (err: unknown) {
      setError(message(err))
    }
  }

  async function copy() {
    if (!note) return
    try {
      await navigator.clipboard.writeText(`${note.subject}\n\n${note.message}`)
      setCopied(true)
    } catch (err: unknown) {
      setError(message(err))
    }
  }

  if (!candidate) return <p className="muted">Loading…</p>

  return (
    <section className="candidate" aria-label={`Candidate ${candidate.title || candidate.id}`}>
      <h4>
        {candidate.title || `Candidate ${candidate.id}`} <span className={`badge state ${stateTone(candidate.state)}`}>{stateLabel(candidate.state)}</span>
      </h4>
      <p className="meta">
        {sourceLabel(candidate.source_kind)} · {seenText(candidate)}
        {candidate.asking_price && ` · ${candidate.asking_price} ${candidate.currency}`}
        {candidate.location && ` · ${candidate.location}`}
        {candidate.included_parts && ` · includes ${candidate.included_parts}`}
        {candidate.model && ` · ${candidate.model} · ${usd(candidate.cost_usd)}`}
        {candidate.from_fixture && <span className="badge">recorded answer</span>}
      </p>
      {candidate.url && (
        <p className="meta">
          Link (saved as is, not opened): <code>{candidate.url}</code>
        </p>
      )}
      {candidate.warnings.length > 0 && (
        <ul className="warnings" aria-label="Reading warnings">
          {candidate.warnings.map((w, i) => (
            <li key={`${i}:${w.slice(0, 24)}`}>{w}</li>
          ))}
        </ul>
      )}
      {candidate.assessment && <Result result={candidate.assessment} />}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <div className="row">
        <button type="button" onClick={() => void askSeller()}>
          Ask the seller
        </button>
        {candidate.state !== 'withdrawn' && (
          <>
            <button type="button" onClick={() => void act(() => api.find.recheck(id))}>
              Recheck
            </button>
            <button type="button" onClick={() => void act(() => api.find.withdraw(id))}>
              Withdraw
            </button>
          </>
        )}
      </div>
      {note && (
        <div className="seller-note">
          <strong>{note.subject}</strong>
          <textarea className="draft-text" readOnly aria-label="Message to the seller" value={note.message} />
          <button type="button" onClick={() => void copy()}>
            {copied ? 'Copied' : 'Copy the message'}
          </button>
        </div>
      )}
    </section>
  )
}
