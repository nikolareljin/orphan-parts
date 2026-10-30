import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { ApiError, api, type Budget, type Conflict, type ItemSummary, type Preferences, type Project, type TemplateSummary } from '../lib/api'
import { usd } from '../lib/format'
import {
  EFFORTS,
  EMPTY_PREFERENCES,
  budgetText,
  canStart,
  conflictText,
  conflictsOf,
  effortLabel,
  missing,
  money,
  numberOrNull, numberProblem,
  skillsFromText,
  skillsToText,
  statusLabel,
  statusTone,
} from '../lib/projects'

function message(err: unknown): string {
  return err instanceof Error ? err.message : String(err)
}

// Build and reuse: what the owner wants, what Muse Spark proposes from the inventory, and the
// projects that come of it. An item is committed to one selected build at a time.
export default function Build() {
  const [projects, setProjects] = useState<Project[]>([])
  const [budget, setBudget] = useState<Budget | null>(null)
  const [openId, setOpenId] = useState<number | null>(null)
  const [error, setError] = useState('')

  const load = useCallback(() => {
    api.build
      .projects()
      .then((list) => {
        setProjects(list.projects)
        setBudget(list.budget)
      })
      .catch((err: unknown) => setError(message(err)))
  }, [])

  useEffect(() => {
    load()
  }, [load])

  return (
    <div className="build">
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <PreferencesForm onSaved={load} />
      <Propose
        onProposed={(list) => {
          load()
          setOpenId(list[0]?.id ?? null)
        }}
      />
      {budget && (
        <p className="meta" aria-label="Budget across selected projects">
          {budgetText(budget)}
        </p>
      )}
      {projects.length === 0 ? (
        <p className="muted">No projects yet. Say what you want above and ask for proposals; they are built from what is in your inventory.</p>
      ) : (
        <table className="evidence" aria-label="Projects">
          <thead>
            <tr>
              <th scope="col">Project</th>
              <th scope="col">Stands</th>
              <th scope="col">Items</th>
              <th scope="col">Missing</th>
              <th scope="col">Spend</th>
              <th scope="col"></th>
            </tr>
          </thead>
          <tbody>
            {projects.map((p) => (
              <tr key={p.id}>
                <td>{p.title}</td>
                <td>
                  <span className={`badge state ${statusTone(p.status)}`}>{statusLabel(p.status)}</span>
                </td>
                <td>{p.allocations.length}</td>
                <td>{missing(p).length}</td>
                <td>{money(p.spend_estimate, p.currency)}</td>
                <td>
                  <button type="button" className="link" onClick={() => setOpenId(p.id)}>
                    Open
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {openId !== null && <ProjectPanel key={openId} id={openId} onChanged={load} onClosed={() => setOpenId(null)} />}
    </div>
  )
}

function PreferencesForm({ onSaved }: { onSaved: () => void }) {
  const [prefs, setPrefs] = useState<Preferences>(EMPTY_PREFERENCES)
  const [skills, setSkills] = useState('')
  const [budget, setBudgetText] = useState('')
  const [radius, setRadius] = useState('')
  const [open, setOpen] = useState(false)
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
        setSkills(skillsToText(p.skills))
        setBudgetText(p.budget === null ? '' : String(p.budget))
        setRadius(p.radius_km === null ? '' : String(p.radius_km))
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [])

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
        skills: skillsFromText(skills),
        budget: numberOrNull(budget),
        radius_km: numberOrNull(radius),
        currency: prefs.currency.trim().toUpperCase() || 'USD',
      })
      setPrefs(kept)
      setSaved(true)
      onSaved()
    } catch (err: unknown) {
      setError(message(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="preferences" onSubmit={(e) => void save(e)} aria-label="What I want from a build">
      <div className="row">
        <h3>What I want from a build</h3>
        <button type="button" className="link" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
          {open ? 'Hide' : 'Edit'}
        </button>
        {!open && (
          <span className="muted">
            {prefs.interests || 'no interests written'} · {effortLabel(prefs.effort)} ·{' '}
            {prefs.budget === null ? 'no budget' : `budget ${money(prefs.budget, prefs.currency)}`}
          </span>
        )}
      </div>
      {open && (
        <>
          <label className="wide">
            <span>Interests</span>
            <textarea
              value={prefs.interests}
              maxLength={2000}
              rows={2}
              placeholder="a desk for the kids' homework, music in the kitchen"
              onChange={(e) => setPrefs({ ...prefs, interests: e.target.value })}
            />
          </label>
          <div className="row">
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
            <label>
              <span>Skills (comma separated)</span>
              <input value={skills} maxLength={400} onChange={(e) => setSkills(e.target.value)} />
            </label>
            <label>
              <span>Tools I have</span>
              <input value={prefs.tools} maxLength={2000} onChange={(e) => setPrefs({ ...prefs, tools: e.target.value })} />
            </label>
            <label className="check">
              <input type="checkbox" checked={prefs.opens_devices} onChange={(e) => setPrefs({ ...prefs, opens_devices: e.target.checked })} />
              <span>I open devices up</span>
            </label>
          </div>
          <div className="row">
            <label>
              <span>Budget</span>
              <input value={budget} inputMode="decimal" onChange={(e) => setBudgetText(e.target.value)} />
            </label>
            <label>
              <span>Currency</span>
              <input value={prefs.currency} maxLength={3} onChange={(e) => setPrefs({ ...prefs, currency: e.target.value.toUpperCase() })} />
            </label>
            <label>
              <span>Radius (km)</span>
              <input value={radius} inputMode="numeric" onChange={(e) => setRadius(e.target.value)} />
            </label>
            <label>
              <span>Buy</span>
              <select value={prefs.purchase} onChange={(e) => setPrefs({ ...prefs, purchase: e.target.value as Preferences['purchase'] })}>
                <option value="used">used</option>
                <option value="new">new</option>
                <option value="either">either</option>
              </select>
            </label>
            <button type="submit" disabled={busy}>
              {busy ? 'Saving…' : 'Save'}
            </button>
            {saved && <span className="muted">saved</span>}
          </div>
        </>
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </form>
  )
}

function Propose({ onProposed }: { onProposed: (list: Project[]) => void }) {
  const [templates, setTemplates] = useState<TemplateSummary[]>([])
  const [count, setCount] = useState(3)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [outcome, setOutcome] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    api.build
      .templates()
      .then(setTemplates)
      .catch(() => undefined)
  }, [])

  async function propose(event: FormEvent) {
    event.preventDefault()
    if (busy) return
    setBusy(true)
    setError('')
    setOutcome('')
    try {
      const list = await api.build.propose(count, note)
      setOutcome(
        list.length === 0
          ? 'Nothing proposed that the inventory backs. Add items, or say more about what you want.'
          : `${list.length} proposed${list[0].from_fixture ? '' : ` for ${usd(list.reduce((sum, p) => sum + p.cost_usd, 0))}`}`,
      )
      onProposed(list)
    } catch (err: unknown) {
      setError(message(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="propose" onSubmit={(e) => void propose(e)} aria-label="Propose projects">
      <h3>What could I build from what I own?</h3>
      <p className="muted">
        Muse Spark reads your inventory and the project templates and proposes builds; only what names items you have is shown. Templates:{' '}
        {templates.map((t) => t.label).join(', ') || '…'}.
      </p>
      <div className="row">
        <label>
          <span>How many</span>
          <select value={count} onChange={(e) => setCount(Number(e.target.value))}>
            {[1, 2, 3, 4, 5].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>This time</span>
          <input value={note} maxLength={2000} placeholder="something for the kids, nothing with soldering" onChange={(e) => setNote(e.target.value)} />
        </label>
        <button type="submit" disabled={busy}>
          {busy ? 'Thinking…' : 'Propose'}
        </button>
        {outcome && <span className="muted">{outcome}</span>}
      </div>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </form>
  )
}

function ProjectPanel({ id, onChanged, onClosed }: { id: number; onChanged: () => void; onClosed: () => void }) {
  const [project, setProject] = useState<Project | null>(null)
  const [conflicts, setConflicts] = useState<Conflict[]>([])
  const [items, setItems] = useState<ItemSummary[]>([])
  const [picked, setPicked] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  // the items an open requirement may be filled with: not gone, not for sale or giving away
  useEffect(() => {
    api.items
      .list()
      .then((list) => setItems(list.filter((i) => i.availability !== 'gone' && i.intent !== 'sell' && i.intent !== 'give')))
      .catch(() => undefined)
  }, [id])

  useEffect(() => {
    let cancelled = false
    api.build
      .project(id)
      .then((p) => {
        if (!cancelled) setProject(p)
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(message(err))
      })
    return () => {
      cancelled = true
    }
  }, [id])

  async function act(call: () => Promise<Project>) {
    if (busy) return
    setBusy(true)
    setError('')
    setConflicts([])
    try {
      setProject(await call())
      onChanged()
    } catch (err: unknown) {
      if (err instanceof ApiError && err.status === 409) setConflicts(conflictsOf(err.body))
      else setError(message(err))
    } finally {
      setBusy(false)
    }
  }

  if (!project) return <p className="muted">Loading…</p>
  const open = missing(project)
  const active = project.status !== 'abandoned' && project.status !== 'done'

  return (
    <article className="project-panel" aria-label={`Project ${project.title}`}>
      <div className="row">
        <h3>{project.title}</h3>
        <span className={`badge state ${statusTone(project.status)}`}>{statusLabel(project.status)}</span>
        <span className="muted">{effortLabel(project.effort)}</span>
        <button type="button" className="link" onClick={onClosed}>
          Close panel
        </button>
      </div>
      <p>{project.result}</p>
      <p className="meta">
        Expected spend {money(project.spend_estimate, project.currency)}
        {project.skills.length > 0 && ` · skills: ${project.skills.join(', ')}`}
        {' · '}
        {project.from_fixture ? 'recorded answer' : `${project.model}, ${usd(project.cost_usd)}`}
      </p>

      <h4>From your inventory</h4>
      {project.allocations.length === 0 ? (
        <p className="muted">No item of yours is on this project any more.</p>
      ) : (
        <ul aria-label="Items on this project">
          {project.allocations.map((a) => (
            <li key={a.item_id}>
              <strong>{a.item_name}</strong> as {a.requirement.replace(/_/g, ' ')}
              {a.committed ? ' (committed)' : ''}
              {a.why && <span className="muted"> · {a.why}</span>}
            </li>
          ))}
        </ul>
      )}

      {open.length > 0 && (
        <>
          <h4>Still needed</h4>
          <ul aria-label="Missing requirements">
            {open.map((r) => (
              <li key={r.key}>
                {r.label}
                {r.blocking ? '' : ' (optional)'}
                {r.search_id !== null ? (
                  <span className="muted"> · search #{r.search_id} open on the Find page</span>
                ) : (
                  active && (
                    <>
                      {' '}
                      <button type="button" className="link" disabled={busy} onClick={() => void act(() => api.build.searchFor(id, r.key))}>
                        Find it on Marketplace
                      </button>
                    </>
                  )
                )}
                {active && items.length > 0 && (
                  <span className="fill">
                    {' '}
                    <select aria-label={`Item for ${r.label}`} value={picked[r.key] ?? ''} onChange={(e) => setPicked({ ...picked, [r.key]: e.target.value })}>
                      <option value="">an item of mine…</option>
                      {items.map((i) => (
                        <option key={i.id} value={i.id}>
                          #{i.id} {i.name} ({i.item_type})
                        </option>
                      ))}
                    </select>{' '}
                    <button
                      type="button"
                      className="link"
                      disabled={busy || !picked[r.key]}
                      onClick={() => void act(() => api.build.fill(id, r.key, Number(picked[r.key])))}
                    >
                      Use it
                    </button>
                  </span>
                )}
              </li>
            ))}
          </ul>
        </>
      )}

      {project.unknowns.length > 0 && (
        <>
          <h4>Check before starting</h4>
          <ul aria-label="Unknowns">
            {project.unknowns.map((u) => (
              <li key={u}>{u}</li>
            ))}
          </ul>
        </>
      )}
      {project.safety.length > 0 && (
        <ul className="safety" aria-label="Safety">
          {project.safety.map((s) => (
            <li key={s}>{s}</li>
          ))}
        </ul>
      )}
      {project.steps.length > 0 && (
        <details>
          <summary>Steps</summary>
          <ol>
            {project.steps.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ol>
          {project.sources.length > 0 && <p className="muted">Guidance: {project.sources.join('; ')}</p>}
        </details>
      )}
      {project.dropped.length > 0 && (
        <p className="muted" aria-label="Dropped lines">
          Left out, as the inventory does not back it: {project.dropped.join('; ')}
        </p>
      )}

      {conflicts.length > 0 && (
        <p className="error" role="alert">
          {conflictText(conflicts)}.{' '}
          <button type="button" className="link" disabled={busy} onClick={() => void act(() => api.build.select(id, true))}>
            Move it here
          </button>
        </p>
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <div className="row actions">
        {(project.status === 'proposed' || project.status === 'shortlisted') && (
          <>
            {project.status === 'proposed' && (
              <button type="button" disabled={busy} onClick={() => void act(() => api.build.shortlist(id))}>
                Shortlist
              </button>
            )}
            <button type="button" disabled={busy} onClick={() => void act(() => api.build.select(id))}>
              Select and commit the items
            </button>
          </>
        )}
        {project.status === 'selected' && (
          <button type="button" disabled={busy || !canStart(project)} title={canStart(project) ? '' : 'a blocking requirement is missing'} onClick={() => void act(() => api.build.advance(id, 'building'))}>
            Start building
          </button>
        )}
        {project.status === 'building' && (
          <button type="button" disabled={busy} onClick={() => void act(() => api.build.advance(id, 'done'))}>
            Mark done
          </button>
        )}
        {active && (
          <button type="button" className="link" disabled={busy} onClick={() => void act(() => api.build.abandon(id))}>
            Abandon
          </button>
        )}
      </div>
    </article>
  )
}
