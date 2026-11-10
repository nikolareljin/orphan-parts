import { useEffect, useState } from 'react'
import { PAIRS, PHASE_MS, builtSrc, local, partSrc, remember, seen, stepAfter } from '../lib/showcase'

interface Props {
  open?: boolean // shown or not, whatever this browser remembers (the tests)
}

export default function Showcase({ open: openAtFirst }: Props) {
  // read once: the visit is remembered as soon as it shows, so a reload does not show it again
  const [open, setOpen] = useState(() => openAtFirst ?? !seen(local()))
  const [step, setStep] = useState(0)

  useEffect(() => {
    if (open) remember(local())
  }, [open])

  useEffect(() => {
    if (!open) return
    const timer = window.setInterval(() => setStep(stepAfter), PHASE_MS)
    return () => window.clearInterval(timer)
  }, [open])

  if (!open) return null
  const current = Math.floor(step / 2)
  const built = step % 2 === 1
  const pair = PAIRS[current]
  return (
    <section className="card showcase" aria-label="What a spare part can become">
      <button type="button" className="modal-close showcase-close" aria-label="Close" onClick={() => setOpen(false)}>
        ×
      </button>
      <div className="showcase-stage">
        {/* the shown pair and the next one: the next is loaded before its turn */}
        {PAIRS.map((p, i) =>
          i === current || i === (current + 1) % PAIRS.length ? (
            <figure key={p.name} className={`showcase-pair${i === current ? ' is-current' : ''}${i === current && built ? ' is-built' : ''}`} aria-hidden={i !== current}>
              <img className="showcase-built" src={builtSrc(p)} alt={`${p.from} as ${p.to}, drawn by Muse Image`} width="960" height="720" />
              <img className="showcase-part" src={partSrc(p)} alt={p.from} width="960" height="720" />
            </figure>
          ) : null,
        )}
      </div>
      <div className="showcase-text">
        <h2>Every spare part has a second life</h2>
        <p className="showcase-caption" aria-live="polite">
          <strong>{pair.from}</strong>
          <span className={`showcase-arrow${built ? ' is-built' : ''}`}> → {pair.to}</span>
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
