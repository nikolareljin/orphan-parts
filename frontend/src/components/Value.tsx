import { useEffect, useState, type FormEvent } from 'react'
import { api, type Guidance, type Item, type PriceReport } from '../lib/api'
import { usd } from '../lib/format'
import { evidenceText, kindLabel, money, rangeText, searchesText } from '../lib/value'

function message(err: unknown): string {
  return err instanceof Error ? err.message : String(err)
}

// What it is worth: four quantities kept apart, each with its pages and dates. You set the price.
// `onGuided` is told when a new guidance is written, so a panel that reads it can read it again.
export default function Value({ item, onGuided }: { item: Item; onGuided?: () => void }) {
  const [guide, setGuide] = useState<Guidance | null>(null)
  const [reports, setReports] = useState<PriceReport[]>([])
  const [currency, setCurrency] = useState('USD')
  const [country, setCountry] = useState('')
  const [city, setCity] = useState('')
  const [price, setPrice] = useState('')
  const [soldOn, setSoldOn] = useState('')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    Promise.all([api.value.history(item.id), api.value.reports(item.id)])
      .then(([history, list]) => {
        if (cancelled) return
        // a request made meanwhile may already hold a newer guidance; the history must not
        // put an older one, or none, over it
        const latest = history.length > 0 ? history[history.length - 1] : null
        setGuide((current) => (latest === null || (current && current.id > latest.id) ? current : latest))
        setReports(list)
      })
      .catch(() => {
        if (!cancelled) {
          setGuide(null)
          setReports([])
        }
      })
    return () => {
      cancelled = true
    }
    // the item's version too: an edit after the guidance is what makes it stale
  }, [item.id, item.version])

  async function ask(event: FormEvent) {
    event.preventDefault()
    if (busy) return
    setBusy(true)
    setError('')
    try {
      setGuide(await api.value.guide(item.id, { currency, country, city }))
      onGuided?.()
    } catch (err: unknown) {
      setError(message(err))
    } finally {
      setBusy(false)
    }
  }

  async function record(event: FormEvent) {
    event.preventDefault()
    if (busy) return
    setBusy(true)
    setError('')
    try {
      await api.value.report(item.id, { price: Number(price), currency, sold_on: soldOn, note })
      setReports(await api.value.reports(item.id))
      setPrice('')
      setSoldOn('')
      setNote('')
    } catch (err: unknown) {
      setError(message(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="value" aria-label="What is it worth?">
      <h4>What is it worth?</h4>
      <form onSubmit={(e) => void ask(e)}>
        <div className="row">
          <label>
            <span>Currency</span>
            <input value={currency} maxLength={3} onChange={(e) => setCurrency(e.target.value.toUpperCase())} />
          </label>
          <label>
            <span>Country</span>
            <input value={country} maxLength={2} placeholder="US" onChange={(e) => setCountry(e.target.value.toUpperCase())} />
          </label>
          <label>
            <span>City</span>
            <input value={city} maxLength={80} placeholder="for local results" onChange={(e) => setCity(e.target.value)} />
          </label>
          <button type="submit" disabled={busy || currency.length !== 3}>
            {busy ? 'Working…' : 'Price guidance'}
          </button>
        </div>
      </form>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {guide && <GuidanceView guide={guide} />}
      <form onSubmit={(e) => void record(e)} aria-label="Record a sale you know">
        <h5>Record a sale you know</h5>
        <div className="row">
          <label>
            <span>Price ({currency})</span>
            <input value={price} inputMode="decimal" onChange={(e) => setPrice(e.target.value)} />
          </label>
          <label>
            <span>Sold on</span>
            <input type="date" value={soldOn} onChange={(e) => setSoldOn(e.target.value)} />
          </label>
          <label>
            <span>Note</span>
            <input value={note} maxLength={200} placeholder="yours, or one you saw" onChange={(e) => setNote(e.target.value)} />
          </label>
          <button type="submit" disabled={busy || !price || !soldOn}>
            Record
          </button>
        </div>
      </form>
      {reports.length > 0 && (
        <ul className="reports" aria-label="Sales you reported">
          {reports.map((r) => (
            <li key={r.id}>
              {money(r.price, r.currency)} on {r.sold_on}
              {r.note && <small className="muted"> · {r.note}</small>}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

function GuidanceView({ guide }: { guide: Guidance }) {
  return (
    <div className="guidance" role="status" aria-label={`Guidance ${guide.version}`}>
      <p className="meta">
        {guide.model} · {usd(guide.cost_usd)} · {searchesText(guide.searches)} · {evidenceText(guide)}
        {guide.from_fixture && <span className="badge">recorded answer</span>}
        {guide.stale && <span className="badge">item changed since</span>}
      </p>
      {guide.weak && <p className="hint weak">Weak evidence: {guide.weak_reason}.</p>}
      <table className="evidence quantities" aria-label="Quantities">
        <thead>
          <tr>
            <th scope="col">Figure</th>
            <th scope="col">Count</th>
            <th scope="col">Range</th>
            <th scope="col">Typical</th>
            <th scope="col">Basis</th>
          </tr>
        </thead>
        <tbody>
          {guide.quantities.map((q) => (
            <tr key={q.kind}>
              <td>{q.label}</td>
              <td>{q.count}</td>
              <td>{rangeText(q)}</td>
              <td>{money(q.typical, q.currency)}</td>
              <td>{q.basis}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <h5>Ways to price</h5>
      <ul className="strategies" aria-label="Ways to price">
        {guide.strategies.map((s) => (
          <li key={s.name}>
            <strong>{s.label}</strong> {money(s.price, guide.currency)} <small className="muted">{s.note}</small>
          </li>
        ))}
      </ul>
      {guide.comparables.length > 0 && (
        <>
          <h5>Comparables</h5>
          <ul className="comparables" aria-label="Comparables">
            {guide.comparables.map((c, i) => (
              <li key={`${i}:${c.source_url}`}>
                <span className={`badge kind ${c.kind}`}>{kindLabel(c.kind)}</span>{' '}
                <a href={c.source_url} target="_blank" rel="noopener noreferrer">
                  {c.title}
                </a>{' '}
                {money(c.price, c.currency)}
                <small className="muted">
                  {' '}
                  {c.condition && `${c.condition} · `}seen {c.observed}
                </small>
              </li>
            ))}
          </ul>
        </>
      )}
      {guide.caveats.length > 0 && (
        <ul className="warnings" aria-label="Caveats">
          {guide.caveats.map((w, i) => (
            <li key={`${i}:${w.slice(0, 24)}`}>{w}</li>
          ))}
        </ul>
      )}
      {guide.parts && <p className="meta">Whole or parts: {guide.parts.note}.</p>}
    </div>
  )
}
