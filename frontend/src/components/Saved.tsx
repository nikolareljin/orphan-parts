import { STEPS, earlierLabel, type Step } from '../lib/runs'

// Before a step was ever asked: what it does, what it gives back and what one asking costs, so
// the section is never an empty panel. The button that asks sits beside it, the owner's alone.
export function NeverRun({ step }: { step: Step }) {
  const s = STEPS[step]
  return (
    <div className="never-run" role="note" aria-label="Nothing asked yet">
      <p>
        <strong>Nothing asked yet.</strong> {s.what}
      </p>
      <p>
        <span className="label">You get</span> {s.gives}
      </p>
      <p className="muted">{s.cost}</p>
    </div>
  )
}

// Every answer kept for a step, newest first, with the one shown marked: picking one shows it
// as it was kept. Nothing is asked of a model; asking again adds a version, never replaces one.
export function Earlier<T extends { id: number; version: number; at: string; model: string; from_fixture?: boolean }>({
  items,
  shown,
  onPick,
  what = 'results',
}: {
  items: T[]
  shown: number | null
  onPick: (item: T) => void
  what?: string
}) {
  if (items.length < 2) return null
  const newestFirst = [...items].reverse()
  return (
    <details className="earlier">
      <summary>
        Earlier {what} ({items.length - 1})
      </summary>
      <ul aria-label={`Earlier ${what}`}>
        {newestFirst.map((r) => (
          <li key={r.id}>
            {r.id === shown ? (
              <span aria-current="true">
                {earlierLabel(r)} <span className="badge">shown</span>
              </span>
            ) : (
              <button type="button" className="link" onClick={() => onPick(r)}>
                {earlierLabel(r)}
              </button>
            )}
          </li>
        ))}
      </ul>
    </details>
  )
}
