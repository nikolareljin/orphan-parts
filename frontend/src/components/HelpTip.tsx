import { useEffect, useId, useLayoutEffect, useRef, useState, type KeyboardEvent } from 'react'
import { docsUrl, helpNext, type HelpAction, type HelpEntry } from '../lib/help'

// A small "?" beside a heading or a control: a click or a tap opens a short note on what can be
// done there and how, with a link to the matching page of the docs. It is a disclosure, not a
// dialog: Escape, a click outside or the close button ends it, and focus goes back to the "?".
// Inside the item dialog, Escape closes the note and leaves the dialog open.
export default function HelpTip({ entry, defaultOpen = false }: { entry: HelpEntry; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen)
  const [shift, setShift] = useState(0)
  const wrap = useRef<HTMLSpanElement>(null)
  const toggle = useRef<HTMLButtonElement>(null)
  const pop = useRef<HTMLSpanElement>(null)
  const id = useId()

  function act(action: HelpAction, refocus = false) {
    setOpen((was) => helpNext(was, action))
    if (refocus) toggle.current?.focus()
  }

  // a press anywhere else closes it; the "?" itself toggles on its own
  useEffect(() => {
    if (!open) return
    const outside = (event: PointerEvent) => {
      if (wrap.current && !wrap.current.contains(event.target as Node)) setOpen((was) => helpNext(was, 'outside'))
    }
    document.addEventListener('pointerdown', outside)
    return () => document.removeEventListener('pointerdown', outside)
  }, [open])

  // kept inside the view, or inside the dialog's body when it is in one
  useLayoutEffect(() => {
    if (!open) {
      setShift(0)
      return
    }
    const el = pop.current
    if (!el) return
    const bound = el.closest('.modal-body')?.getBoundingClientRect() ?? { left: 0, right: window.innerWidth }
    const rect = el.getBoundingClientRect()
    const margin = 8
    const left = rect.left - shift
    const right = rect.right - shift
    if (right > bound.right - margin) setShift(bound.right - margin - right)
    else if (left < bound.left + margin) setShift(bound.left + margin - left)
    // measured once per opening
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  function onKeyDown(event: KeyboardEvent) {
    if (event.key !== 'Escape' || !open) return
    // the note, not the dialog it may sit in
    event.preventDefault()
    event.stopPropagation()
    act('escape', true)
  }

  return (
    <span className="help-tip" ref={wrap} onKeyDown={onKeyDown}>
      <button
        ref={toggle}
        type="button"
        className="link help-tip-toggle"
        aria-label={`Help: ${entry.topic}`}
        aria-expanded={open}
        aria-controls={open ? id : undefined}
        onClick={() => act('toggle')}
      >
        ?
      </button>
      {open && (
        <span ref={pop} id={id} className="help-tip-pop" role="group" aria-label={`About: ${entry.topic}`} style={shift ? { transform: `translateX(${shift}px)` } : undefined}>
          <button type="button" className="link help-tip-close" aria-label="Dismiss help" onClick={() => act('close', true)}>
            ×
          </button>
          <span className="help-tip-text">{entry.text}</span>
          {entry.doc && (
            <a className="help-tip-doc" href={docsUrl(entry.doc)} target="_blank" rel="noreferrer">
              More in the docs
            </a>
          )}
        </span>
      )}
    </span>
  )
}
