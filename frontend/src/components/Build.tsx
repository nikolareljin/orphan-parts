import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { ApiError, api, type Budget, type Conflict, type ItemSummary, type Pack, type Preferences, type Project, type TemplateSummary } from '../lib/api'
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
  numberOrNull,
  numberProblem,
  packLabel,
  progressText,
  statusLabel,
  statusTone,
  stepDone,
  todayIso,
} from '../lib/projects'
import { skillsLine } from '../lib/profile'
import Compatibility from './Compatibility'
import DrawIt from './DrawIt'
import Modal from './Modal'
import Markdown from './Markdown'
import { NeverRun } from './Saved'
import SignInLine from './SignInLine'
import HelpTip from './HelpTip'
import { HELP } from '../lib/help'

function message(err: unknown): string {
  return err instanceof Error ? err.message : String(err)
}

// Build and reuse: what the owner wants, what Muse Spark proposes from the inventory, and the
// projects that come of it. An item is committed to one selected build at a time. The demo
// visitor reads the projects built on public items as the owner left them, without the budget;
// every button that saves, proposes, commits or draws is the sign-in line.
export default function Build({ demo = false }: { demo?: boolean }) {
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
      <PreferencesForm demo={demo} onSaved={load} />
      <Propose
        demo={demo}
        onProposed={(list) => {
          load()
          setOpenId(list[0]?.id ?? null)
        }}
      />
      {budget && !demo && (
        <p className="meta" aria-label="Budget across selected projects">
          {budgetText(budget)}
        </p>
      )}
      {projects.length === 0 ? (
        demo ? (
          <p className="muted">No projects to show yet.</p>
        ) : (
          <>
            <p className="muted">No projects yet. Press Propose above; ideas only use items in your inventory.</p>
            <NeverRun step="propose" />
          </>
        )
      ) : (
        <table className="evidence" aria-label="Projects">
          <thead>
            <tr>
              <th scope="col">Project</th>
              <th scope="col">Status</th>
              <th scope="col">Items</th>
              <th scope="col">Missing</th>
              <th scope="col">Est. cost</th>
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
      {openId !== null && (
        <Modal title={`Project #${openId}`} onClose={() => setOpenId(null)}>
          <ProjectPanel key={openId} id={openId} demo={demo} onChanged={load} onClosed={() => setOpenId(null)} />
        </Modal>
      )}
    </div>
  )
}

function PreferencesForm({ demo, onSaved }: { demo: boolean; onSaved: () => void }) {
  const [prefs, setPrefs] = useState<Preferences>(EMPTY_PREFERENCES)
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
    <form className="preferences fields" onSubmit={(e) => void save(e)} aria-label="What I want from a build">
      <div className="row">
        <h3>What I want from a build</h3>
        <HelpTip entry={demo ? HELP.buildPrefsVisitor : HELP.buildPrefs} />
        {!demo && (
          <button type="button" className="link" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
            {open ? 'Hide' : 'Edit'}
          </button>
        )}
        {(demo || !open) && (
          <span className="muted">
            {prefs.interests || 'no interests set'} · {effortLabel(prefs.effort)}
            {/* the owner's budget is not shown to the demo visitor */}
            {!demo && <> · {prefs.budget === null ? 'no budget' : `budget ${money(prefs.budget, prefs.currency)}`}</>}
            {demo && prefs.skills.length > 0 && <> · skills: {skillsLine(prefs.skills)}</>}
          </span>
        )}
      </div>
      {open && !demo && (
        <>
          <div className="row">
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
            <p className="skills-line">
              <span>Skills</span> {skillsLine(prefs.skills)} · <a href="#profile">rate them on your Profile</a>
            </p>
            <label>
              <span>Tools I have</span>
              <input value={prefs.tools} maxLength={2000} onChange={(e) => setPrefs({ ...prefs, tools: e.target.value })} />
            </label>
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
              <span>Buy parts</span>
              <select value={prefs.purchase} onChange={(e) => setPrefs({ ...prefs, purchase: e.target.value as Preferences['purchase'] })}>
                <option value="used">used</option>
                <option value="new">new</option>
                <option value="either">either</option>
              </select>
            </label>
            <label className="check">
              <input type="checkbox" checked={prefs.opens_devices} onChange={(e) => setPrefs({ ...prefs, opens_devices: e.target.checked })} />
              <span>I am OK opening up devices</span>
            </label>
          </div>
          <div className="row actions">
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

function Propose({ demo, onProposed }: { demo: boolean; onProposed: (list: Project[]) => void }) {
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
    if (busy || demo) return
    setBusy(true)
    setError('')
    setOutcome('')
    try {
      const list = await api.build.propose(count, note)
      setOutcome(
        list.length === 0
          ? 'No idea fits what you own. Add items, or say more about what you want.'
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
    <form className="propose fields" onSubmit={(e) => void propose(e)} aria-label="Propose projects">
      <div className="section-head">
        <h3>What could I build from what I own?</h3>
        <HelpTip entry={demo ? HELP.proposeVisitor : HELP.propose} />
      </div>
      <p className="muted">
        Muse Spark suggests builds from your inventory and the project templates; only ideas that use items you own are shown. Templates:{' '}
        {templates.map((t) => t.label).join(', ') || '…'}.
      </p>
      {demo ? (
        <SignInLine what="Propose" />
      ) : (
        <ProposeControls count={count} note={note} busy={busy} outcome={outcome} onCount={setCount} onNote={setNote} />
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </form>
  )
}

function ProposeControls({
  count,
  note,
  busy,
  outcome,
  onCount,
  onNote,
}: {
  count: number
  note: string
  busy: boolean
  outcome: string
  onCount: (n: number) => void
  onNote: (text: string) => void
}) {
  return (
    <>
      <div className="row">
        <label>
          <span>How many</span>
          <select value={count} onChange={(e) => onCount(Number(e.target.value))}>
            {[1, 2, 3, 4, 5].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Anything else this time</span>
          <input value={note} maxLength={2000} placeholder="something for the kids, nothing with soldering" onChange={(e) => onNote(e.target.value)} />
        </label>
      </div>
      <div className="row actions">
        <button type="submit" disabled={busy}>
          {busy ? 'Thinking…' : 'Propose'}
        </button>
        {outcome && <span className="muted">{outcome}</span>}
      </div>
    </>
  )
}

function ProjectPanel({ id, demo, onChanged, onClosed }: { id: number; demo: boolean; onChanged: () => void; onClosed: () => void }) {
  const [project, setProject] = useState<Project | null>(null)
  const [conflicts, setConflicts] = useState<Conflict[]>([])
  const [items, setItems] = useState<ItemSummary[]>([])
  const [picked, setPicked] = useState<Record<string, string>>({})
  const [swapTo, setSwapTo] = useState<Record<number, string>>({})
  const [packs, setPacks] = useState<Pack[]>([])
  const [ticks, setTicks] = useState<boolean[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  // a tick shows at once and is reconciled with what the project says once it is saved
  useEffect(() => {
    setTicks(project?.progress ?? [])
  }, [project])

  // the packs written so far; reloaded with the project, since a change marks them stale
  const loadPacks = useCallback(() => {
    api.build
      .packs(id)
      .then(setPacks)
      .catch(() => undefined)
  }, [id])

  // the items an open requirement may be filled with: not gone, not for sale or giving away
  useEffect(() => {
    if (demo) return
    api.items
      .list()
      .then((list) => setItems(list.filter((i) => i.availability !== 'gone' && i.intent !== 'sell' && i.intent !== 'give')))
      .catch(() => undefined)
  }, [id, demo])

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

  useEffect(() => {
    loadPacks()
  }, [loadPacks])

  // Every change goes through here; it says whether the server took it, so a control shown
  // ahead of the answer can go back to what the project says.
  async function act(call: () => Promise<Project>): Promise<boolean> {
    if (busy) return false
    setBusy(true)
    setError('')
    setConflicts([])
    try {
      setProject(await call())
      onChanged()
      loadPacks()
      return true
    } catch (err: unknown) {
      if (err instanceof ApiError && err.status === 409) setConflicts(conflictsOf(err.body))
      else setError(message(err))
      return false
    } finally {
      setBusy(false)
    }
  }

  async function writePack() {
    if (busy) return
    setBusy(true)
    setError('')
    try {
      await api.build.writePack(id)
      loadPacks()
    } catch (err: unknown) {
      setError(message(err))
    } finally {
      setBusy(false)
    }
  }

  if (!project) return <p className="muted">Loading…</p>
  const open = missing(project)
  const active = project.status !== 'abandoned' && project.status !== 'done'
  const underway = project.status === 'selected' || project.status === 'building' || project.status === 'done'

  return (
    <article className="project-panel" aria-label={`Project ${project.title}`}>
      <div className="row">
        <h3>{project.title}</h3>
        <span className={`badge state ${statusTone(project.status)}`}>{statusLabel(project.status)}</span>
        <span className="muted">{effortLabel(project.effort)}</span>
        <HelpTip entry={demo ? HELP.projectVisitor : HELP.project} />
        <button type="button" className="link" onClick={onClosed}>
          Close panel
        </button>
      </div>
      <p>{project.result}</p>
      <p className="meta">
        Estimated cost {money(project.spend_estimate, project.currency)}
        {project.skills.length > 0 && ` · skills: ${project.skills.join(', ')}`}
        {' · '}
        {project.from_fixture ? 'recorded answer' : `${project.model}, ${usd(project.cost_usd)}`}
      </p>
      <DrawIt
        key={project.id}
        name={project.title}
        demo={demo}
        shownToDemo
        list={() => api.build.pictures(id)}
        draw={() => api.build.drawPicture(id)}
        url={(n) => api.build.pictureUrl(id, n)}
      />

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
              {active && !demo && (
                // a wrong pick fixed by hand: another item of yours in its place, or none
                <span className="fill">
                  {' '}
                  <select
                    aria-label={`Swap ${a.item_name} for`}
                    value={swapTo[a.item_id] ?? ''}
                    onChange={(e) => setSwapTo({ ...swapTo, [a.item_id]: e.target.value })}
                  >
                    <option value="">swap for…</option>
                    {items
                      .filter((i) => !project.allocations.some((b) => b.item_id === i.id))
                      .map((i) => (
                        <option key={i.id} value={i.id}>
                          #{i.id} {i.name} ({i.item_type})
                        </option>
                      ))}
                  </select>{' '}
                  <button
                    type="button"
                    className="link"
                    disabled={busy || !swapTo[a.item_id]}
                    onClick={() => void act(() => api.build.swap(id, a.item_id, Number(swapTo[a.item_id])))}
                  >
                    Swap
                  </button>{' '}
                  <button type="button" className="link" disabled={busy} onClick={() => void act(() => api.build.remove(id, a.item_id))}>
                    Take it off
                  </button>
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
      {(project.compatibility ?? []).length > 0 && (
        <>
          <h4>Compatibility</h4>
          <Compatibility pairings={project.compatibility ?? []} />
        </>
      )}

      {open.length > 0 && (
        <>
          <div className="section-head">
            <h4>Still needed</h4>
            <HelpTip entry={demo ? HELP.stillNeededVisitor : HELP.stillNeeded} />
          </div>
          <ul aria-label="Missing requirements">
            {open.map((r) => (
              <li key={r.key}>
                {r.label}
                {r.blocking ? '' : ' (optional)'}
                {r.incompatible && <span className="error"> · {r.incompatible}</span>}
                {r.need && <span className="muted"> · what fits: {r.need}</span>}
                {r.instead && r.instead_id && (
                  <span className="muted">
                    {' '}
                    · yours that fits: {r.instead}
                    {active && !demo && (
                      <>
                        {' '}
                        <button
                          type="button"
                          className="link"
                          disabled={busy}
                          onClick={() => void act(() => api.build.fill(id, r.key, Number(r.instead_id)))}
                        >
                          Use {r.instead}
                        </button>
                      </>
                    )}
                  </span>
                )}{' '}
                <a
                  href={marketplaceSearch(r.need || r.label)}
                  target="_blank"
                  rel="noopener noreferrer"
                  aria-label={`Search Marketplace for ${r.label}`}
                >
                  Search Marketplace
                </a>
                {r.search_id !== null ? (
                  <span className="muted"> · search #{r.search_id} open on Find a part</span>
                ) : (
                  active &&
                  !demo && (
                    <>
                      {' '}
                      <button type="button" className="link" disabled={busy} onClick={() => void act(() => api.build.searchFor(id, r.key))}>
                        Find it on Marketplace
                      </button>
                    </>
                  )
                )}
                {active && !demo && items.length > 0 && (
                  <span className="fill">
                    {' '}
                    <select aria-label={`Item for ${r.label}`} value={picked[r.key] ?? ''} onChange={(e) => setPicked({ ...picked, [r.key]: e.target.value })}>
                      <option value="">pick one of my items…</option>
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
      {project.steps.length > 0 && !underway && (
        // the visitor reads the project whole: the steps are open for them
        <details open={demo}>
          <summary>Steps</summary>
          <ol>
            {project.steps.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ol>
          {project.sources.length > 0 && <p className="muted">Sources: {project.sources.join('; ')}</p>}
        </details>
      )}
      {project.steps.length > 0 && underway && (
        <>
          <h4>
            Steps <span className="muted">{progressText(project)}</span>
          </h4>
          <ol className="progress" aria-label="Progress">
            {project.steps.map((s, i) => (
              <li key={s}>
                <label>
                  <input
                    type="checkbox"
                    checked={stepDone({ progress: ticks }, i)}
                    disabled={busy || demo || project.status === 'done'}
                    onChange={(e) => {
                      const before = ticks
                      const next = project.steps.map((_, n) => (n === i ? e.target.checked : stepDone({ progress: ticks }, n)))
                      setTicks(next)
                      void act(() => api.build.setProgress(id, i, e.target.checked)).then((ok) => {
                        if (!ok) setTicks(before)
                      })
                    }}
                  />{' '}
                  {s}
                </label>
              </li>
            ))}
          </ol>
          {project.sources.length > 0 && <p className="muted">Sources: {project.sources.join('; ')}</p>}
        </>
      )}
      {(underway || packs.length > 0) && (
        <section className="packs" aria-label="Build pack">
          <h4>Build pack</h4>
          <p className="muted">
            One document with the goal, your items and their accepted values, what is still needed, costs, steps, safety notes, open questions and
            limits. Made from your data with no model call; it goes out of date when an item, the project or the budget changes.
          </p>
          {demo ? (
            <SignInLine what="Write the build pack" />
          ) : (
            underway && (
            <div className="row">
              <button type="button" disabled={busy} onClick={() => void writePack()}>
                {packs.length > 0 ? 'Write it again' : 'Write the build pack'}
              </button>
            </div>
            )
          )}
          {packs.length > 0 && <PackShown packs={packs} />}
        </section>
      )}
      {(project.status === 'building' || project.status === 'done') && (demo ? <OutcomeShown project={project} /> : <OutcomeSection project={project} busy={busy} onAct={act} />)}
      {project.dropped.length > 0 && (
        <p className="muted" aria-label="Dropped lines">
          Left out (not in your inventory): {project.dropped.join('; ')}
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
      {demo ? (
        <SignInLine what="Shortlist, select, build or abandon" />
      ) : (
        <ProjectActions project={project} busy={busy} onAct={act} />
      )}
    </article>
  )
}

// The buttons that move a project along; the owner's alone.
function ProjectActions({ project, busy, onAct: act }: { project: Project; busy: boolean; onAct: (call: () => Promise<Project>) => Promise<boolean> }) {
  const id = project.id
  const active = project.status !== 'abandoned' && project.status !== 'done'
  return (
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
        <button type="button" disabled={busy || !canStart(project)} title={canStart(project) ? '' : 'a required part is still missing'} onClick={() => void act(() => api.build.advance(id, 'building'))}>
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
  )
}

// The outcome as the demo visitor reads it: only once the owner shared it, never the form.
function OutcomeShown({ project }: { project: Project }) {
  const outcome = project.outcome
  if (!outcome) return null
  return (
    <section className="outcome" aria-label="Outcome">
      <h4>Outcome</h4>
      <p className="meta" aria-label="Recorded outcome">
        Tested {outcome.tested_on}: {outcome.working ? 'working' : 'not working'}. {outcome.configuration}; {outcome.test}
        {outcome.limitations ? `; limitations: ${outcome.limitations}` : ''}
      </p>
    </section>
  )
}


// What was built and how it was tested, in the owner's words; working marks the project done.
function OutcomeSection({ project, busy, onAct }: { project: Project; busy: boolean; onAct: (call: () => Promise<Project>) => Promise<boolean> }) {
  const [configuration, setConfiguration] = useState(project.outcome?.configuration ?? '')
  const [test, setTest] = useState(project.outcome?.test ?? '')
  const [testedOn, setTestedOn] = useState(project.outcome?.tested_on ?? todayIso())
  const [working, setWorking] = useState(project.outcome?.working ?? true)
  const [limitations, setLimitations] = useState(project.outcome?.limitations ?? '')
  const [shareText, setShareText] = useState('')
  const [shareError, setShareError] = useState('')
  const outcome = project.outcome
  const shared = outcome?.shared ?? false
  const [shareOn, setShareOn] = useState(shared)

  useEffect(() => {
    setShareOn(shared)
  }, [shared])

  useEffect(() => {
    if (!shared) {
      setShareText('')
      return
    }
    let cancelled = false
    api.build
      .shareText(project.id)
      .then((t) => {
        if (cancelled) return
        setShareText(t.text)
        setShareError('')
      })
      .catch((err: unknown) => {
        if (!cancelled) setShareError(message(err))
      })
    return () => {
      cancelled = true
    }
  }, [project.id, shared, project.version])

  function record(event: FormEvent) {
    event.preventDefault()
    void onAct(() => api.build.recordOutcome(project.id, { configuration, test, tested_on: testedOn, working, limitations }))
  }

  return (
    <section className="outcome" aria-label="Outcome">
      <h4>Outcome</h4>
      {outcome && (
        <p className="meta" aria-label="Recorded outcome">
          Tested {outcome.tested_on}: {outcome.working ? 'working' : 'not working'}. {outcome.configuration}; {outcome.test}
          {outcome.limitations ? `; limitations: ${outcome.limitations}` : ''}
        </p>
      )}
      {project.status === 'building' && (
        <form className="fields" onSubmit={record} aria-label="Record the outcome">
          <div className="row">
            <label className="wide">
              <span>What was set up</span>
              <input value={configuration} maxLength={2000} placeholder="the tool seated on the wand" onChange={(e) => setConfiguration(e.target.value)} />
            </label>
            <label className="wide">
              <span>How it was tested</span>
              <input value={test} maxLength={2000} placeholder="ran it over the stairs for a minute" onChange={(e) => setTest(e.target.value)} />
            </label>
          </div>
          <div className="row">
            <label>
              <span>Tested on</span>
              <input value={testedOn} placeholder="YYYY-MM-DD" onChange={(e) => setTestedOn(e.target.value)} />
            </label>
            <label>
              <span>Limitations</span>
              <input value={limitations} maxLength={2000} onChange={(e) => setLimitations(e.target.value)} />
            </label>
            <label className="check">
              <input type="checkbox" checked={working} onChange={(e) => setWorking(e.target.checked)} />
              <span>It works</span>
            </label>
          </div>
          <div className="row actions">
            <button type="submit" disabled={busy || !configuration.trim() || !test.trim()}>
              Record the outcome
            </button>
          </div>
        </form>
      )}
      {outcome && (
        <div className="share">
          <label className="check">
            <input
              type="checkbox"
              checked={shareOn}
              disabled={busy}
              onChange={(e) => {
                const wanted = e.target.checked
                setShareOn(wanted)
                void onAct(() => api.build.setShared(project.id, wanted)).then((ok) => {
                  if (!ok) setShareOn(!wanted)
                })
              }}
            />
            <span>Share the outcome (item types, result, setup, test and limitations; no names, values, places or prices)</span>
          </label>
          {shared && shareText && (
            <label className="wide">
              <span>Text to share</span>
              <textarea aria-label="Share text" readOnly value={shareText} rows={6} />
            </label>
          )}
          {shareError && (
            <p className="error" role="alert">
              {shareError}
            </p>
          )}
        </div>
      )}
    </section>
  )
}

// The build pack read in place (the latest unless an earlier one is picked), and every version
// listed with the Markdown file to download.
function PackShown({ packs }: { packs: Pack[] }) {
  const [shown, setShown] = useState<number | null>(null)
  const pack = packs.find((p) => p.id === shown) ?? packs[packs.length - 1]
  return (
    <>
      <ul aria-label="Packs">
        {[...packs].reverse().map((p) => (
          <li key={p.id}>
            <a href={api.build.packUrl(p.id)} download>
              Download
            </a>{' '}
            {packLabel(p)}{' '}
            {p.id === pack.id ? (
              <span className="badge">shown below</span>
            ) : (
              <button type="button" className="link" onClick={() => setShown(p.id)}>
                Show
              </button>
            )}
          </li>
        ))}
      </ul>
      <Markdown text={pack.markdown} label={`Build pack ${pack.version}`} />
    </>
  )
}

// A Marketplace search for what a project still needs, opened by the owner or the visitor: the
// requirement's words before the first comma or "or", which is what a seller would title it.
function marketplaceSearch(label: string): string {
  const words = label.split(/,| or /)[0].replace(/^(an?|the)\s+/i, '').trim()
  return `https://www.facebook.com/marketplace/search/?query=${encodeURIComponent(words)}`
}
