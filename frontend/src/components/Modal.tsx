import { useLayoutEffect, useRef, type ReactNode } from 'react'

// One dialog for every panel that opens from a list: the page behind stays where it was,
// Escape and the close button end it, focus stays inside. The panel's own heading and
// controls are rendered as they are; the dialog adds only the frame.
export default function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null)
  // the latest handler, so the dialog is opened once and not on every render of the parent
  const close = useRef(onClose)
  close.current = onClose
  // a click counts as the backdrop's only when the press started there too: a drag that
  // starts in a field and ends outside must not throw the panel away
  const pressedBackdrop = useRef(false)

  // a layout effect: its cleanup runs while the dialog is still in the document, so the
  // browser hands focus back to the button that opened it
  useLayoutEffect(() => {
    const dialog = ref.current
    if (!dialog) return
    if (!dialog.open) dialog.showModal()
    const cancel = (event: Event) => {
      event.preventDefault()
      close.current()
    }
    // a close the platform does on its own (a back gesture, a close watcher that would not be
    // cancelled) tells the page the same way, so the panel's state follows the dialog's
    // the event is delivered after the fact: a dialog already open again (a strict-mode
    // remount closes and reopens it in one go) has nothing to tell
    const closed = () => {
      if (!dialog.open) close.current()
    }
    dialog.addEventListener('cancel', cancel)
    dialog.addEventListener('close', closed)
    document.body.classList.add('has-dialog')
    return () => {
      dialog.removeEventListener('cancel', cancel)
      dialog.removeEventListener('close', closed)
      document.body.classList.remove('has-dialog')
      if (dialog.open) dialog.close()
    }
  }, [])

  return (
    <dialog
      ref={ref}
      className="modal"
      aria-label={title}
      onPointerDown={(event) => {
        pressedBackdrop.current = event.target === event.currentTarget
      }}
      onClick={(event) => {
        // a click on the backdrop lands on the dialog element itself, not on its content
        if (event.target === event.currentTarget && pressedBackdrop.current) onClose()
        pressedBackdrop.current = false
      }}
    >
      <div className="modal-frame">
        <div className="modal-bar">
          <span className="modal-title">{title}</span>
          <button type="button" className="modal-close" aria-label="Close" onClick={onClose}>
            ×
          </button>
        </div>
        <div className="modal-body">{children}</div>
      </div>
    </dialog>
  )
}
