import { useEffect, useState, type FormEvent } from 'react'
import { api, type Preferences, type RatedSkill, type SkillLevel } from '../lib/api'
import { EFFORTS, EMPTY_PREFERENCES, numberOrNull, numberProblem } from '../lib/projects'
import { LEVELS, SKILL_MAX, customProblem, isStarter, skillRows, skillsToSave } from '../lib/profile'

function message(err: unknown): string {
  return err instanceof Error ? err.message : String(err)
}

// The owner's profile: what they can do and what they have, kept once. The scenarios on an item
// are written for it, and so is every build proposal. It is the same record as the Build page's
// preferences; the skills are rated here.
export default function Profile() {
  const [prefs, setPrefs] = useState<Preferences>(EMPTY_PREFERENCES)
  const [rows, setRows] = useState<RatedSkill[]>(() => skillRows([]))
  const [custom, setCustom] = useState('')
  const [customLevel, setCustomLevel] = useState<SkillLevel>('some')
  const [budget, setBudget] = useState('')
  const [radius, setRadius] = useState('')
  const [busy, setBusy] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    api.build
      .preferences()
      .then((p) => {
        if (cancelled) return
        setPrefs(p)
        setRows(skillRows(p.skills))
        setBudget(p.budget === null ? '' : String(p.budget))
        setRadius(p.radius_km === null ? '' : String(p.radius_km))
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(message(err))
      })
    return () => {
      cancelled = true
    }
  }, [])

  function rate(index: number, level: SkillLevel) {
    setRows((current) => current.map((r, i) => (i === index ? { ...r, level } : r)))
    setSaved(false)
  }

  function addCustom() {
    const problem = customProblem(custom, rows)
    if (problem) {
      setError(problem)
      return
    }
    setRows((current) => [...current, { skill: custom.trim().replace(/\s+/g, ' '), level: customLevel }])
    setCustom('')
    setCustomLevel('some')
    setError('')
    setSaved(false)
  }

  async function save(event: FormEvent) {
    event.preventDefault()
    if (busy) return
    const problem = numberProblem(budget, 'The budget') ?? numberProblem(radius, 'The radius')
    if (problem) {
      setError(problem)
      setSaved(false)
      return
    }
    setBusy(true)
    setError('')
    setSaved(false)
    try {
      const kept = await api.build.setPreferences({
        ...prefs,
        skills: skillsToSave(rows),
        budget: numberOrNull(budget),
        radius_km: numberOrNull(radius),
        currency: prefs.currency.trim().toUpperCase() || 'USD',
      })
      setPrefs(kept)
      setRows(skillRows(kept.skills))
      setSaved(true)
    } catch (err: unknown) {
      setError(message(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="profile" onSubmit={(e) => void save(e)} aria-label="Profile">
      <p className="muted">
        What you can do and what you have. The scenarios on an item (keep and fix, reuse, sell or give away) are written for it,
        and so are the build proposals. One profile for this inventory.
      </p>

      <h3>Skills</h3>
      <div className="table-wrap">
      <table className="evidence skills" aria-label="Skills">
        <thead>
          <tr>
            <th scope="col">Skill</th>
            {LEVELS.map((l) => (
              <th key={l.value} scope="col">
                {l.label}
              </th>
            ))}
            <th scope="col" aria-label="Remove" />
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={row.skill}>
              <th scope="row">{row.skill}</th>
              {LEVELS.map((l) => (
                <td key={l.value}>
                  <input
                    type="radio"
                    name={`skill-${i}`}
                    aria-label={`${row.skill}: ${l.label}`}
                    checked={row.level === l.value}
                    onChange={() => rate(i, l.value)}
                  />
                </td>
              ))}
              <td>
                {!isStarter(row.skill) && (
                  <button
                    type="button"
                    className="link"
                    aria-label={`Remove ${row.skill}`}
                    onClick={() => {
                      setRows((current) => current.filter((_, j) => j !== i))
                      setSaved(false)
                    }}
                  >
                    Remove
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
      <div className="row">
        <label>
          <span>Another skill</span>
          <input
            value={custom}
            maxLength={SKILL_MAX}
            placeholder="bike repair"
            onChange={(e) => setCustom(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault()
                addCustom()
              }
            }}
          />
        </label>
        <label>
          <span>Level</span>
          <select value={customLevel} onChange={(e) => setCustomLevel(e.target.value as SkillLevel)}>
            {LEVELS.map((l) => (
              <option key={l.value} value={l.value}>
                {l.label}
              </option>
            ))}
          </select>
        </label>
        <button type="button" onClick={addCustom} disabled={!custom.trim()}>
          Add skill
        </button>
      </div>

      <h3>What you have and how you work</h3>
      <div className="row">
        <label className="wide">
          <span>Tools I have</span>
          <input
            value={prefs.tools}
            maxLength={2000}
            placeholder="soldering iron, multimeter, drill"
            onChange={(e) => setPrefs({ ...prefs, tools: e.target.value })}
          />
        </label>
        <label>
          <span>Effort I will put in</span>
          <select value={prefs.effort} onChange={(e) => setPrefs({ ...prefs, effort: e.target.value as Preferences['effort'] })}>
            {EFFORTS.map((e) => (
              <option key={e.value} value={e.value}>
                {e.label}
              </option>
            ))}
          </select>
        </label>
        <label className="check">
          <input type="checkbox" checked={prefs.opens_devices} onChange={(e) => setPrefs({ ...prefs, opens_devices: e.target.checked })} />
          <span>I am OK opening up devices</span>
        </label>
      </div>
      <div className="row">
        <label>
          <span>Budget</span>
          <input value={budget} inputMode="decimal" onChange={(e) => setBudget(e.target.value)} />
        </label>
        <label>
          <span>Currency</span>
          <input value={prefs.currency} maxLength={3} onChange={(e) => setPrefs({ ...prefs, currency: e.target.value.toUpperCase() })} />
        </label>
        <label>
          <span>Radius (km)</span>
          <input value={radius} inputMode="numeric" onChange={(e) => setRadius(e.target.value)} />
        </label>
      </div>
      <div className="row">
        <button type="submit" disabled={busy}>
          {busy ? 'Saving…' : 'Save profile'}
        </button>
        {saved && <span className="muted">saved</span>}
      </div>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </form>
  )
}
