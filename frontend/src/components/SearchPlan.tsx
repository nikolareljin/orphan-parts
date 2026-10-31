import { useCallback, useEffect, useState, type ChangeEvent, type FormEvent } from 'react'
import { api, type BroughtListing, type Candidate, type Item, type ListingScore, type PatternResult, type Search } from '../lib/api'
import { usd } from '../lib/format'
import { askingPrice, highlightSegments, maxPriceLine, splitListings, stateLabel, stateTone, verdictLabel, verdictTone } from '../lib/find'

const TEST_DELAY_MS = 350
const MAX_SCREENSHOTS = 6

function message(err: unknown): string {
  return err instanceof Error ? err.message : String(err)
}

function today(): string {
  return new Date().toISOString().slice(0, 10)
}

// The plain line about what the app does and does not do on Marketplace.
export function MarketplaceLimit() {
  return (
    <p className="muted plan-limit">
      Marketplace has no public search API, and automating or scraping it is against its terms. These are search links you open and run yourself; bring back what you find by pasting it or with a
      screenshot. Marketplace&apos;s search box does not take regular expressions: the pattern below is applied here, to the listings you bring back.
    </p>
  )
}

function ListingText({ text, score }: { text: string; score: ListingScore }) {
  return (
    <p className="listing-text">
      {highlightSegments(text, score.highlights).map((s, i) =>
        s.kind ? (
          <mark key={i} className={`hit-${s.kind}`} title={s.kind === 'match' ? 'matches the pattern' : 'an exclusion word'}>
            {s.text}
          </mark>
        ) : (
          <span key={i}>{s.text}</span>
        ),
      )}
    </p>
  )
}

function Verdict({ score }: { score: ListingScore }) {
  return <span className={`badge state ${verdictTone(score.verdict)}`}>{verdictLabel(score.verdict)}</span>
}

// Plan the search, keep the pattern, bring listings back and rank them, check the fit of one.
export default function SearchPlan({ search, onChanged, onCandidate }: { search: Search; onChanged: (s: Search) => void; onCandidate?: (c: Candidate) => void }) {
  const plan = search.plan
  const [busy, setBusy] = useState(false)
  const [copied, setCopied] = useState<number | null>(null)
  const [listings, setListings] = useState<BroughtListing[]>([])
  const [error, setError] = useState('')

  const loadListings = useCallback(() => {
    api.find
      .listings(search.id)
      .then(setListings)
      .catch((err: unknown) => setError(message(err)))
  }, [search.id])

  // the ranking changes with the plan: a new pattern scores every listing again
  const planStamp = `${plan?.planned_at ?? ''}|${plan?.edited_at ?? ''}`
  useEffect(() => {
    loadListings()
  }, [loadListings, planStamp])

  async function planIt() {
    if (busy) return
    setBusy(true)
    setError('')
    try {
      onChanged(await api.find.plan(search.id))
    } catch (err: unknown) {
      setError(message(err))
    } finally {
      setBusy(false)
    }
  }

  async function copy(i: number, text: string) {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(i)
    } catch (err: unknown) {
      setError(message(err))
    }
  }

  const closed = search.status === 'closed'

  return (
    <div className="search-plan">
      <section aria-label="Plan the search">
        <h4>Plan the search</h4>
        <MarketplaceLimit />
        {plan && plan.phrasings.length > 0 && (
          <>
            <ol className="phrasings" aria-label="Search phrasings">
              {plan.phrasings.map((p, i) => (
                <li key={`${i}:${p.text}`}>
                  <a href={p.url} target="_blank" rel="noopener noreferrer">
                    {p.text}
                  </a>{' '}
                  <button type="button" className="link" aria-label={`Copy ${p.text}`} onClick={() => void copy(i, p.text)}>
                    {copied === i ? 'Copied' : 'Copy'}
                  </button>
                  {p.why && <span className="muted"> · {p.why}</span>}
                </li>
              ))}
            </ol>
            <p className="meta">
              {maxPriceLine(plan.max_price)}
              {plan.radius_km !== null && ` Within ${plan.radius_km} km: set the distance in Marketplace's location filter, the links do not carry it.`}
              {plan.model && ` · ${plan.model} · ${usd(plan.cost_usd)}`}
              {plan.from_fixture && plan.model && <span className="badge">recorded answer</span>}
            </p>
          </>
        )}
        <div className="row">
          <button type="button" onClick={() => void planIt()} disabled={busy}>
            {busy ? 'Planning…' : plan?.model ? 'Plan again' : 'Plan the search'}
          </button>
          <span className="muted">one Muse Spark call: phrasings, a match pattern and exclusion words</span>
        </div>
        {/* a new plan starts the editor over; saving a word or the pattern keeps the test line */}
        <PatternEditor key={plan?.model ? plan.planned_at : 'by-hand'} search={search} onSaved={onChanged} />
      </section>

      <section aria-label="Bring back listings">
        <h4>Bring back listings</h4>
        {closed ? <p className="muted">This search is closed; reopen it to bring listings back.</p> : <BringBack searchId={search.id} onAdded={setListings} />}
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        {listings.length > 0 && <Ranked searchId={search.id} listings={listings} onListings={setListings} onCandidate={onCandidate} />}
      </section>
    </div>
  )
}

function PatternEditor({ search, onSaved }: { search: Search; onSaved: (s: Search) => void }) {
  const plan = search.plan
  const [pattern, setPattern] = useState(plan?.pattern ?? '')
  const [exclusions, setExclusions] = useState<string[]>(plan?.exclusions ?? ['for parts', 'parts only', 'broken', 'not working', 'does not work'])
  const [word, setWord] = useState('')
  const [sample, setSample] = useState('')
  const [tried, setTried] = useState<PatternResult | null>(null)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState('')

  // the live test: the backend runs the same checks and the same engine as the ranking
  useEffect(() => {
    if (!sample.trim() && !pattern.trim()) {
      setTried(null)
      return
    }
    let cancelled = false
    const timer = window.setTimeout(() => {
      api.find
        .testPattern({
          pattern,
          exclusions,
          max_price: search.max_price,
          text: sample || ' ',
        })
        .then((r) => {
          if (!cancelled) setTried(r)
        })
        .catch(() => undefined)
    }, TEST_DELAY_MS)
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [pattern, exclusions, sample, search.max_price])

  async function save(next: { pattern?: string; exclusions?: string[] }) {
    setError('')
    try {
      const kept = await api.find.editPlan(search.id, next)
      // the chips and the pattern as the backend kept them: trimmed, lower-cased, one of each
      if (kept.plan) {
        setExclusions(kept.plan.exclusions)
        if (next.pattern !== undefined) setPattern(kept.plan.pattern)
      }
      onSaved(kept)
      setSaved(true)
    } catch (err: unknown) {
      setError(message(err))
    }
  }

  function addWord(event: FormEvent) {
    event.preventDefault()
    const w = word.trim().toLowerCase()
    if (!w || exclusions.includes(w)) return
    const next = [...exclusions, w]
    setExclusions(next)
    setWord('')
    void save({ exclusions: next })
  }

  function removeWord(w: string) {
    const next = exclusions.filter((x) => x !== w)
    setExclusions(next)
    void save({ exclusions: next })
  }

  const changed = pattern !== (plan?.pattern ?? '')

  return (
    <div className="pattern-editor">
      {plan?.pattern_error && <p className="warnings">{plan.pattern_error}</p>}
      <form
        className="row"
        aria-label="Match pattern"
        onSubmit={(e) => {
          e.preventDefault()
          void save({ pattern })
        }}
      >
        <label className="pattern">
          <span>Words to match (pattern)</span>
          <input
            value={pattern}
            aria-describedby="pattern-hint"
            maxLength={300}
            spellCheck={false}
            placeholder="OP-?065-?19-?333|19\.5\s*V.{0,20}3\.3\d?\s*A"
            onChange={(e) => {
              setPattern(e.target.value)
              setSaved(false)
            }}
          />
        </label>
        <button type="submit" disabled={!changed || Boolean(tried?.error)}>
          Save pattern
        </button>
        {saved && !changed && <span className="muted">Saved. Listings are ranked by it.</span>}
      </form>
      <p id="pattern-hint" className="meta">
        advanced: a regular expression
      </p>
      {plan?.suggested_pattern && plan.suggested_pattern !== pattern && (
        <p className="meta suggested">
          Planned again, Muse Spark suggests <code>{plan.suggested_pattern}</code>; your saved pattern stays until you save another.{' '}
          <button type="button" className="link" onClick={() => setPattern(plan.suggested_pattern)}>
            Try the suggestion
          </button>
        </p>
      )}
      {/* read out as it changes while typing, without interrupting */}
      <div className="pattern-live" aria-live="polite">
        {tried?.error && <p className="error">{tried.error}</p>}
      </div>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <div className="chips" aria-label="Exclusion words">
        <span className="muted">Skip listings with:</span>
        {exclusions.map((w) => (
          <span key={w} className="chip">
            {w}
            <button type="button" className="link" aria-label={`Remove ${w}`} onClick={() => removeWord(w)}>
              ×
            </button>
          </span>
        ))}
        <form onSubmit={addWord} className="chip-add">
          <input value={word} maxLength={40} aria-label="Add a word to skip" placeholder="Add a word to skip" onChange={(e) => setWord(e.target.value)} />
        </form>
      </div>
      <label className="wide">
        <span>Test the pattern</span>
        <textarea rows={2} value={sample} placeholder="paste a listing title or a line of one" onChange={(e) => setSample(e.target.value)} />
      </label>
      {tried?.score && sample.trim() && (
        <div className="pattern-test" aria-label="Pattern test">
          <Verdict score={tried.score} /> <span className="muted">{tried.score.reasons.join('; ')}</span>
          <ListingText text={sample} score={tried.score} />
        </div>
      )}
    </div>
  )
}

function BringBack({ searchId, onAdded }: { searchId: number; onAdded: (list: BroughtListing[]) => void }) {
  const [text, setText] = useState('')
  const [shots, setShots] = useState<File[]>([])
  const [observedOn, setObservedOn] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const pieces = splitListings(text)

  async function run(action: () => Promise<BroughtListing[]>, clear: () => void) {
    if (busy) return
    setBusy(true)
    setError('')
    try {
      onAdded(await action())
      clear()
    } catch (err: unknown) {
      setError(message(err))
    } finally {
      setBusy(false)
    }
  }

  function onFiles(event: ChangeEvent<HTMLInputElement>) {
    setShots(Array.from(event.target.files ?? []).slice(0, MAX_SCREENSHOTS))
  }

  return (
    <form
      className="bring-back"
      aria-label="Bring back listings"
      onSubmit={(e) => {
        e.preventDefault()
        void run(
          () => api.find.addListings(searchId, pieces, observedOn),
          () => setText(''),
        )
      }}
    >
      <label className="wide">
        <span>Paste one or more listings (separate them with --- or a blank line)</span>
        <textarea rows={6} maxLength={60000} value={text} placeholder={'DVI-D dual link cable, 6 ft, $5\n---\nVGA monitor cable 6 ft, $3'} onChange={(e) => setText(e.target.value)} />
      </label>
      <div className="row">
        <label>
          <span>Seen on</span>
          <input type="date" value={observedOn} max={today()} onChange={(e) => setObservedOn(e.target.value)} />
        </label>
        <button type="submit" disabled={busy || pieces.length === 0 || pieces.length > 20}>
          {busy ? 'Working…' : pieces.length > 1 ? `Score ${pieces.length} listings` : 'Score the listing'}
        </button>
        <span className="muted">Free: ranked here by your words and price, no model call</span>
      </div>
      <div className="row">
        <label>
          <span>Or screenshots (up to {MAX_SCREENSHOTS})</span>
          <input type="file" accept="image/*" multiple onChange={onFiles} />
        </label>
        <button
          type="button"
          disabled={busy || shots.length === 0}
          onClick={() =>
            void run(
              () => api.find.addListingScreenshots(searchId, shots, observedOn),
              () => setShots([]),
            )
          }
        >
          {shots.length > 1 ? `Read ${shots.length} screenshots` : 'Read the screenshot'}
        </button>
        <span className="muted">Each screenshot is read once, then ranked like pasted text</span>
      </div>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </form>
  )
}

function Ranked({ searchId, listings, onListings, onCandidate }: { searchId: number; listings: BroughtListing[]; onListings: (list: BroughtListing[]) => void; onCandidate?: (c: Candidate) => void }) {
  const [checking, setChecking] = useState<number | null>(null)
  const [checked, setChecked] = useState<Record<number, Candidate>>({})
  const [error, setError] = useState('')

  async function check(listing: BroughtListing) {
    if (checking !== null) return
    setChecking(listing.id)
    setError('')
    try {
      const candidate = listing.candidate_id !== null ? await api.find.candidate(listing.candidate_id) : await api.find.checkListing(searchId, listing.id)
      setChecked((all) => ({ ...all, [listing.id]: candidate }))
      if (listing.candidate_id === null) onListings(await api.find.listings(searchId))
      onCandidate?.(candidate)
    } catch (err: unknown) {
      setError(message(err))
    } finally {
      setChecking(null)
    }
  }

  async function remove(listing: BroughtListing) {
    try {
      onListings(await api.find.removeListing(searchId, listing.id))
    } catch (err: unknown) {
      setError(message(err))
    }
  }

  return (
    <>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <ol className="ranked" aria-label="Listings brought back, ranked">
        {listings.map((b) => {
          const candidate = checked[b.id]
          return (
            <li key={b.id} className={`ranked-${b.score.verdict}`} aria-label={`Listing ${b.id}`}>
              <div className="row">
                <Verdict score={b.score} />
                {b.score.price !== null && <strong>{askingPrice(b.score.price)}</strong>}
                <span className="muted">{b.score.reasons.join('; ')}</span>
                <span className="muted">
                  · {b.source_kind === 'screenshot' ? 'screenshot' : 'pasted'}, seen {b.observed_on}
                </span>
              </div>
              <ListingText text={b.text} score={b.score} />
              <div className="row">
                <button type="button" onClick={() => void check(b)} disabled={checking !== null}>
                  {checking === b.id ? 'Checking…' : b.candidate_id !== null ? 'Show the fit' : 'Check fit'}
                </button>
                <button type="button" className="link" onClick={() => void remove(b)}>
                  Remove
                </button>
                {b.candidate_id === null && <span className="muted">One Muse Spark reading, then the profile&apos;s fit rules</span>}
              </div>
              {candidate && (
                <div className="fit" aria-label={`Fit of listing ${b.id}`}>
                  <span className={`badge state ${stateTone(candidate.state)}`}>{stateLabel(candidate.state)}</span> {candidate.assessment && <span>{candidate.assessment.summary}</span>}
                  {candidate.questions.length > 0 ? (
                    <>
                      <p className="meta">Ask the seller:</p>
                      <ul className="questions">
                        {candidate.questions.map((q) => (
                          <li key={q}>{q}</li>
                        ))}
                      </ul>
                    </>
                  ) : (
                    <p className="meta">Nothing left to ask the seller by the rules.</p>
                  )}
                  <p className="meta">Candidate #{candidate.id}: open it in the search for the full checks and the message to send.</p>
                </div>
              )}
            </li>
          )
        })}
      </ol>
    </>
  )
}

// The item dialog's way in: the item's open search with its plan, or a line to start one.
export function ItemSearch({ item }: { item: Item }) {
  const [search, setSearch] = useState<Search | null>(null)
  const [loaded, setLoaded] = useState(false)
  const [title, setTitle] = useState('')
  const [maxPrice, setMaxPrice] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    api.find
      .searches()
      .then((all) => {
        if (cancelled) return
        setSearch(all.find((s) => s.need_item_id === item.id && s.status !== 'closed') ?? null)
        setLoaded(true)
      })
      .catch(() => {
        if (!cancelled) setLoaded(true)
      })
    return () => {
      cancelled = true
    }
  }, [item.id])

  async function start(event: FormEvent) {
    event.preventDefault()
    setError('')
    try {
      setSearch(
        await api.find.create({
          need_item_id: item.id,
          profile: item.profile ? '' : 'generic_item',
          title,
          spec: {},
          max_price: maxPrice.trim() ? Number(maxPrice) : null,
          currency: 'USD',
          radius_km: null,
        }),
      )
    } catch (err: unknown) {
      setError(message(err))
    }
  }

  if (!loaded) return null
  return (
    <section className="item-search" aria-label="Find one on Marketplace">
      <h4>Find one on Marketplace</h4>
      {search ? (
        <>
          <p className="meta">
            Search #{search.id}: {search.title}
            {search.max_price !== null && search.max_price > 0 && `, up to ${askingPrice(search.max_price)}`}
          </p>
          <SearchPlan search={search} onChanged={setSearch} />
        </>
      ) : (
        <form className="row" aria-label="Start a search for this item" onSubmit={(e) => void start(e)}>
          <label>
            <span>Looking for</span>
            <input value={title} maxLength={200} placeholder="the part this item needs" onChange={(e) => setTitle(e.target.value)} />
          </label>
          <label>
            <span>Max price ($)</span>
            <input value={maxPrice} inputMode="decimal" onChange={(e) => setMaxPrice(e.target.value)} />
          </label>
          <button type="submit" disabled={!title.trim()}>
            Start the search
          </button>
        </form>
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </section>
  )
}
