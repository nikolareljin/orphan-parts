import { useEffect, useState } from 'react'
import { LAST_STEP, PAIRS, PHASE_MS, builtSrc, local, partSrc, remember, seen, stepAfter, stillMotion } from '../lib/showcase'

interface Props {
  open?: boolean // shown or not, whatever this browser remembers (the tests)
}

// after the close button, where the keyboard goes on: the page that is open
function focusThePage() {
  document.querySelector<HTMLElement>('.nav button[aria-current="page"]')?.focus()
}

export default function Showcase({ open: openAtFirst }: Props) {
  // read once: the visit is remembered as soon as it shows, so a reload does not show it again
  const [open, setOpen] = useState(() => openAtFirst ?? !seen(local()))
  const [still] = useState(stillMotion)
  const [step, setStep] = useState(() => (still ? 1 : 0))

  useEffect(() => {
    if (open) remember(local())
  }, [open])

  useEffect(() => {
    if (!open || still || step >= LAST_STEP) return
    const timer = window.setTimeout(() => setStep(stepAfter), PHASE_MS)
    return () => window.clearTimeout(timer)
  }, [open, still, step])

  if (!open) return null
  const current = Math.floor(step / 2)
  const built = step % 2 === 1
  const pair = PAIRS[current]
  return (
    <section className="card showcase" aria-label="What a spare part can become">
      <button
        type="button"
        className="modal-close showcase-close"
        aria-label="Close the welcome"
        onClick={() => {
          setOpen(false)
          focusThePage()
        }}
      >
        ×
      </button>
      {/* pictures only: the caption says what they show */}
      <div className="showcase-stage" aria-hidden="true">
        {/* the pair before stays under the shown one while it fades in; the next is loaded ahead */}
        {PAIRS.map((p, i) =>
          Math.abs(i - current) <= 1 ? (
            <figure key={p.name} className={`showcase-pair${i === current ? ' is-current' : ''}${i === current && built ? ' is-built' : ''}${i < current ? ' is-before' : ''}`}>
              <img className="showcase-built" src={builtSrc(p)} alt="" width="960" height="720" />
              <span className="showcase-inset">
                <img className="showcase-part" src={partSrc(p)} alt="" width="960" height="720" />
              </span>
            </figure>
          ) : null,
        )}
      </div>
      <div className="showcase-text">
        <h2>Every spare part has a second life</h2>
        <p className="showcase-caption">
          <strong>{pair.from}</strong>
          <span className={`showcase-arrow${built ? ' is-built' : ''}`} aria-hidden={!built}>
            {' '}
            → {pair.to}
          </span>
        </p>
        <ol className="showcase-dots" aria-hidden="true">
          {PAIRS.map((p, i) => (
            <li key={p.name} className={i === current ? 'is-current' : undefined} />
          ))}
        </ol>
        <p className="muted showcase-note">
          Parts from the demo set, drawn by Muse Image as what they could become. Illustrative. Read a label, keep it in
          your inventory, and ask what yours could be.
        </p>
      </div>
    </section>
  )
}
