import { useEffect, useState, type FormEvent } from 'react'
import { api, type Assessment, type Item, type ItemSummary, type ProfileRule } from '../lib/api'
import { provenanceLabel } from '../lib/inventory'
import { inputLabel, needSide, ruleHint, rulesNote, statusLabel, verdictLabel, verdictTone } from '../lib/match'

function message(err: unknown): string {
  return err instanceof Error ? err.message : String(err)
}

// This item as a candidate: checked against what another item needs, or values written in.
export default function Assess({ item }: { item: Item }) {
  const [rules, setRules] = useState<ProfileRule[]>([])
  const [others, setOthers] = useState<ItemSummary[]>([])
  const [needItemId, setNeedItemId] = useState<number | null>(null)
  const [values, setValues] = useState<Record<string, string>>({})
  const [result, setResult] = useState<Assessment | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    // another profile means other rules: what was typed for the old ones no longer applies
    setResult(null)
    setValues({})
    setError('')
    if (!item.profile) {
      setRules([])
      return
    }
    api.profiles
      .rules(item.profile)
      .then((list) => {
        if (!cancelled) setRules(list)
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(message(err))
      })
    return () => {
      cancelled = true
    }
  }, [item.profile])

  useEffect(() => {
    let cancelled = false
    api.items
      .list()
      .then((list) => {
        if (!cancelled) setOthers(list.filter((s) => s.id !== item.id))
      })
      .catch(() => {
        if (!cancelled) setOthers([])
      })
    return () => {
      cancelled = true
    }
  }, [item.id])

  async function check(event: FormEvent) {
    event.preventDefault()
    if (busy) return
    setBusy(true)
    setError('')
    try {
      setResult(await api.assess(needSide(needItemId, item.profile, values), { item_id: item.id }))
    } catch (err: unknown) {
      setError(message(err))
    } finally {
      setBusy(false)
    }
  }

  const whoseRules = needItemId === null ? '' : rulesNote(item.profile, others.find((o) => o.id === needItemId)?.profile)

  if (!item.profile) {
    return (
      <section className="assess" aria-label="Does it fit?">
        <h4>Does it fit?</h4>
        <p className="muted">Pick a profile for this item above; its rules decide what a fit means.</p>
      </section>
    )
  }

  return (
    <section className="assess" aria-label="Does it fit?">
      <h4>Does it fit?</h4>
      <form onSubmit={(e) => void check(e)}>
        <div className="row">
          <label>
            <span>Needed by</span>
            <select
              value={needItemId ?? ''}
              onChange={(e) => {
                setNeedItemId(e.target.value === '' ? null : Number(e.target.value))
                setResult(null)
              }}
            >
              <option value="">Values written in below</option>
              {others.map((o) => (
                <option key={o.id} value={o.id}>
                  #{o.id} {o.name}
                </option>
              ))}
            </select>
          </label>
        </div>
        {whoseRules && <p className="hint">{whoseRules}</p>}
        {needItemId === null && (
          <div className="needed">
            {rules.map((rule) => (
              <label key={rule.key} title={ruleHint(rule)}>
                <span>
                  {inputLabel(rule)} <small className="muted">{rule.hard ? 'hard' : 'soft'}, {ruleHint(rule)}</small>
                </span>
                <input
                  value={values[rule.key] ?? ''}
                  onChange={(e) => setValues({ ...values, [rule.key]: e.target.value })}
                />
              </label>
            ))}
          </div>
        )}
        <div className="row">
          <button type="submit" disabled={busy || (needItemId === null && rules.length === 0)}>
            {busy ? 'Checking…' : 'Check fit'}
          </button>
        </div>
      </form>

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {result && <Result result={result} />}
    </section>
  )
}

export function Result({ result }: { result: Assessment }) {
  return (
    <div className={`verdict ${verdictTone(result.verdict)}`} role="status">
      <strong>{verdictLabel(result.verdict)}</strong>
      <span className="muted">
        {result.summary} · rules of {result.profile}
      </span>
      <table className="evidence checks-table" aria-label="Checks">
        <thead>
          <tr>
            <th scope="col">Rule</th>
            <th scope="col">Needed</th>
            <th scope="col">This item</th>
            <th scope="col">Result</th>
            <th scope="col">Basis</th>
          </tr>
        </thead>
        <tbody>
          {result.checks.map((c) => (
            <tr key={c.key}>
              <td>
                {c.label} <small className="muted">{c.hard ? 'hard' : 'soft'}</small>
              </td>
              <td>{c.needed ? `${c.needed} ${c.unit}`.trim() : '—'}</td>
              <td>
                {c.observed ? `${c.observed} ${c.unit}`.trim() : '—'}
                {c.backing && (
                  <small className="muted">
                    {' '}
                    {provenanceLabel(c.backing.provenance)}
                    {c.backing.review === 'proposed' && ', to confirm'}
                    {c.backing.uncertainty !== null && ` ±${c.backing.uncertainty}`}
                  </small>
                )}
              </td>
              <td className={c.status}>{statusLabel(c.status)}</td>
              <td>{c.basis}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {result.questions.length > 0 && (
        <>
          <h5>Ask the seller</h5>
          <ul className="questions" aria-label="Questions">
            {result.questions.map((q) => (
              <li key={q}>{q}</li>
            ))}
          </ul>
        </>
      )}
      {result.missing.length > 0 && (
        <p className="meta">Nothing required for: {result.missing.join(', ')}.</p>
      )}
      {result.to_confirm.length > 0 && (
        <p className="meta">Resting on observations still to confirm: {result.to_confirm.join(', ')}.</p>
      )}
    </div>
  )
}
