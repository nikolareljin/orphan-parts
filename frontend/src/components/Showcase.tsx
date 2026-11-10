import { useEffect, useState } from 'react'
import {
  LAST_STEP,
  PAIRS,
  PHASE_MS,
  askedFor,
  builtSrc,
  local,
  pairStep,
  partSrc,
  remember,
  seen,
  stepAfter,
  stillMotion,
} from '../lib/showcase'

interface Props {
  open?: boolean // shown or not, whatever this browser remembers (the tests)
  onOpenItem?: (name: string) => void // the part's item in the demo, by its name
}

// after the close button, where the keyboard goes on: the page that is open
function focusThePage() {
  document.querySelector<HTMLElement>('.nav button[aria-current="page"]')?.focus()
}

function hashNow(): string {
  try {
    return window.location.hash
  } catch {
    return '' // no window: rendered on the server
  }
}

export default function Showcase({ open: openAtFirst, onOpenItem }: Props) {
  // read once: the visit is remembered as soon as it shows, so a reload does not show it again;
  // #welcome shows it whatever was remembered
  const [open, setOpen] = useState(() => openAtFirst ?? (askedFor(hashNow()) || !seen(local())))
  const [still] = useState(stillMotion)
  const [step, setStep] = useState(() => pairStep(0, still))

  useEffect(() => {
    if (open) remember(local())
  }, [open])

  // the link to #welcome followed on the page: from the start again, in view
  useEffect(() => {
    const asked = () => {
      if (!askedFor(window.location.hash)) return
      setStep(pairStep(0, still))
      setOpen(true)
      window.scrollTo({ top: 0, behavior: still ? 'auto' : 'smooth' })
    }
    window.addEventListener('hashchange', asked)
    return () => window.removeEventListener('hashchange', asked)
  }, [still])

  // on its own, a phase at a time up to the last drawing; a step chosen by hand goes on from there
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
          // the address drops #welcome, so the link plays it again next time it is followed
          if (askedFor(window.location.hash)) window.history.replaceState(null, '', window.location.pathname + window.location.search)
          focusThePage()
        }}
      >
        ×
      </button>
      <div className="showcase-media">
        {/* pictures only: the caption says what they show */}
        <div className="showcase-stage" aria-hidden="true">
          {/* the pair before stays under the shown one, as drawn, while it fades in (a drawing
              covers the stage, so the one before it can go); the next is loaded ahead */}
          {PAIRS.map((p, i) =>
            Math.abs(i - current) <= 1 ? (
              <figure key={p.name} className={`showcase-pair${i === current ? ' is-current' : ''}${i < current || (i === current && built) ? ' is-built' : ''}${i < current ? ' is-before' : ''}`}>
                <img className="showcase-built" src={builtSrc(p)} alt="" width="960" height="720" />
                <span className="showcase-inset">
                  <img className="showcase-part" src={partSrc(p)} alt="" width="960" height="720" />
                </span>
              </figure>
            ) : null,
          )}
        </div>
        <button type="button" className="modal-close showcase-step showcase-prev" aria-label="Previous part" onClick={() => setStep(pairStep(current - 1, still))}>
          &lt;
        </button>
        <button type="button" className="modal-close showcase-step showcase-next" aria-label="Next part" onClick={() => setStep(pairStep(current + 1, still))}>
          &gt;
        </button>
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
        {onOpenItem && (
          <p className="showcase-open">
            <button type="button" className="link" onClick={() => onOpenItem(pair.item)}>
              See the {pair.item} in the demo
            </button>
          </p>
        )}
        <p className="muted showcase-note">
          Parts from the demo set, drawn by Muse Image as what they could become. Illustrative. Read a label, keep it in
          your inventory, and ask what yours could be.
        </p>
      </div>
    </section>
  )
}
