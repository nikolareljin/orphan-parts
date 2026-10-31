import { useEffect, useRef, useState } from 'react'

export type SectionEntry = { id: string; label: string }

// A row of links at the top of a long dialog, one per section: a click scrolls the section
// into view, and the one in view is marked current. The sections are the panel's children
// with a matching ``data-section``; one that renders nothing (an empty wrapper) has no link.
export default function SectionNav({ entries }: { entries: SectionEntry[] }) {
  const ref = useRef<HTMLElement>(null)
  const [present, setPresent] = useState<string[]>([])
  const [current, setCurrent] = useState<string>('')

  useEffect(() => {
    const nav = ref.current
    const panel = nav?.parentElement
    if (!nav || !panel) return
    const scroller = nav.closest('.modal-body') ?? document.documentElement

    const sections = () =>
      entries
        .map((e) => panel.querySelector<HTMLElement>(`:scope > [data-section="${e.id}"]`))
        .filter((el): el is HTMLElement => el !== null && el.childElementCount > 0)

    // the sections there now: a panel that loads its content later changes the list; the
    // same list again is kept as it is, so a change in the bar itself does not render it again
    const sync = () => {
      const next = sections().map((el) => el.dataset.section ?? '')
      setPresent((prev) => (prev.length === next.length && prev.every((id, i) => id === next[i]) ? prev : next))
    }
    const watcher = new MutationObserver(sync)
    watcher.observe(panel, { childList: true, subtree: true })
    sync()

    // the current section: the last one whose top has entered the upper third of the view
    // under the bar; at the end of the scroll the last section, however short it is
    let pending = 0
    const mark = () => {
      pending = 0
      const found = sections()
      if (found.length === 0) return
      const top = scroller.getBoundingClientRect().top + nav.offsetHeight + scroller.clientHeight * 0.3
      const atEnd = scroller.scrollTop + scroller.clientHeight >= scroller.scrollHeight - 2
      let active = found[0]
      for (const el of found) if (el.getBoundingClientRect().top <= top) active = el
      if (atEnd) active = found[found.length - 1]
      setCurrent(active.dataset.section ?? '')
    }
    const onScroll = () => {
      if (!pending) pending = requestAnimationFrame(mark)
    }
    scroller.addEventListener('scroll', onScroll, { passive: true })
    mark()
    return () => {
      watcher.disconnect()
      scroller.removeEventListener('scroll', onScroll)
      if (pending) cancelAnimationFrame(pending)
    }
  }, [entries])

  function go(id: string) {
    const panel = ref.current?.parentElement
    panel?.querySelector(`:scope > [data-section="${id}"]`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  // the bar is in the document from the first render, so the watcher above has it to hang on;
  // with fewer than two sections there is nothing to move between and it stays hidden
  const shown = entries.filter((e) => present.includes(e.id))
  return (
    <nav ref={ref} className="nav item-nav" aria-label="Sections" hidden={shown.length < 2}>
      {shown.map((e) => (
        <button key={e.id} type="button" aria-current={current === e.id ? 'true' : undefined} onClick={() => go(e.id)}>
          {e.label}
        </button>
      ))}
    </nav>
  )
}
