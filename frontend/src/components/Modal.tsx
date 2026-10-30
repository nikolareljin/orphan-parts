import { useEffect, useRef, type ReactNode } from 'react'

// One dialog for every panel that opens from a list: the page behind stays where it was,
// Escape and the close button end it, focus stays inside. The panel's own heading and
// controls are rendered as they are; the dialog adds only the frame.
export default function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null)
  // the latest handler, so the dialog is opened once and not on every render of the parent
  const close = useRef(onClose)
  close.current = onClose

  useEffect(() => {
    const dialog = ref.current
    if (!dialog) return
    if (!dialog.open) dialog.showModal()
    const cancel = (event: Event) => {
      event.preventDefault()
      close.current()
    }
    dialog.addEventListener('cancel', cancel)
    document.body.classList.add('has-dialog')
    return () => {
      dialog.removeEventListener('cancel', cancel)
      document.body.classList.remove('has-dialog')
      if (dialog.open) dialog.close()
    }
  }, [])

  return (
    <dialog
      ref={ref}
      className="modal"
      aria-label={title}
      onClick={(event) => {
        // a click on the backdrop lands on the dialog element itself, not on its content
        if (event.target === event.currentTarget) onClose()
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
