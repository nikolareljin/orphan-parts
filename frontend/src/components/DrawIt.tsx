import { useEffect, useRef, useState } from 'react'
import { ApiError, type FeedbackTarget, type Picture, type PictureList } from '../lib/api'
import { DRAW_AGAIN_HINT, DRAW_DEMO_LINE, DRAW_HINT, DRAW_OFF_LINE, PROJECT_PICTURE_LABEL, drawState, pictureCaption, shownPictures } from '../lib/picture'
import GatedImage from './GatedImage'
import Feedback from './Feedback'

function message(err: unknown): string {
  return err instanceof Error ? err.message : String(err)
}

// "Draw it" for a finished project: how a reuse card's or a Build project's result could look,
// drawn by Muse Image only when the button is clicked (every click is one paid call; nothing is
// drawn when the card appears). The pictures already drawn are listed, labeled as drawn. The
// server says whether it draws (PICTURE_ENABLED); while it does not, one line says so and there
// is no button. The demo visitor gets the line to sign in in place of the button, and nothing is
// read for them unless the pictures are theirs to see (a project built on public items). A list
// that cannot be read hides it all.
export default function DrawIt({
  name,
  demo,
  shownToDemo = false,
  list,
  draw,
  url,
  feedback,
}: {
  // what is drawn, for the button's accessible name
  name: string
  demo: boolean
  // whether the demo visitor may read the pictures already drawn
  shownToDemo?: boolean
  list: () => Promise<PictureList>
  draw: () => Promise<Picture>
  url: (n: number) => string
  // what a like or a dislike of picture n is about
  feedback?: (n: number) => FeedbackTarget
}) {
  const [enabled, setEnabled] = useState<boolean | null>(null)
  const [pictures, setPictures] = useState<Picture[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [failed, setFailed] = useState(false)

  // the list is read once per card (the parent keys it): the callback is new on every render
  const listOnce = useRef(list)

  useEffect(() => {
    if (demo && !shownToDemo) return
    let cancelled = false
    listOnce
      .current()
      .then((found) => {
        if (cancelled) return
        setEnabled(found.enabled)
        setPictures(found.pictures)
      })
      .catch(() => {
        if (!cancelled) setFailed(true)
      })
    return () => {
      cancelled = true
    }
  }, [demo, shownToDemo])

  async function onDraw() {
    if (busy || demo || !enabled) return
    setBusy(true)
    setError('')
    try {
      const drawn = await draw()
      setPictures((kept) => [...kept.filter((p) => p.n !== drawn.n), drawn])
    } catch (err: unknown) {
      if (err instanceof ApiError && err.status === 503) setEnabled(false)
      else setError(message(err))
    } finally {
      setBusy(false)
    }
  }

  // a list that cannot be read hides the section, as on the item dialog
  if (failed) return null
  const state = drawState(demo, enabled)
  // a picture already drawn stays: drawing again adds one beside it
  const again = pictures.length > 0
  return (
    <div className="draw-it">
      {state === 'off' ? (
        <p className="muted">{DRAW_OFF_LINE}</p>
      ) : state === 'demo' ? (
        // the visitor reads what was drawn; drawing (again) is the owner's, so no button
        <p className="hint">{DRAW_DEMO_LINE}</p>
      ) : (
        <p className="row">
          <button
            type="button"
            className="draw"
            onClick={() => void onDraw()}
            disabled={state !== 'ready' || busy}
            aria-label={`${again ? 'Draw again' : 'Draw it'}: ${name}`}
          >
            {busy ? 'Drawing…' : again ? 'Draw again' : 'Draw it'}
          </button>
          <span className="hint">{again ? DRAW_AGAIN_HINT : DRAW_HINT}</span>
        </p>
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {shownPictures(pictures).map((p) => (
        <figure key={p.n} className="drawn">
          <GatedImage src={url(p.n)} alt={`Illustrative picture ${p.n}: ${p.use}`} loading="lazy" />
          <figcaption>{pictureCaption(p, PROJECT_PICTURE_LABEL)}</figcaption>
          {feedback && <Feedback target={feedback(p.n)} what="drawing" />}
        </figure>
      ))}
    </div>
  )
}
