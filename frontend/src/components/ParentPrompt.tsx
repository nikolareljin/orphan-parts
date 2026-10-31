import { useState, type ChangeEvent } from 'react'
import { api, type Item } from '../lib/api'
import { PARENT_PROMPT, parentPhotoLine } from '../lib/inventory'
import SignInLine from './SignInLine'

// The question about a part the app cannot tie to its device. The owner answers in words or
// with a photo of the device; the demo visitor reads the question and nothing to fill in.
// ``save`` runs a change and keeps the item as the server answered it; a refusal is said by
// the caller, where it says its other refusals.
export default function ParentPrompt({ item, readOnly, save }: { item: Item; readOnly: boolean; save: (action: () => Promise<Item>) => Promise<void> }) {
  const [device, setDevice] = useState('')
  const [busy, setBusy] = useState(false)
  const [line, setLine] = useState('')

  async function run(action: () => Promise<Item>) {
    if (busy) return
    setBusy(true)
    try {
      await save(action)
      setDevice('')
    } catch {
      // said by the caller
    } finally {
      setBusy(false)
    }
  }

  function onText() {
    const value = device.trim()
    if (!value) return
    void run(() => api.items.addField(item.id, { field: 'parent_device', value, provenance: 'owner_reported' }))
  }

  function onPhoto(event: ChangeEvent<HTMLInputElement>) {
    const photo = event.target.files?.[0]
    event.target.value = ''
    if (!photo) return
    void run(async () => {
      const read = await api.items.addParentPhoto(item.id, photo)
      setLine(parentPhotoLine(read.model))
      return read.item
    })
  }

  return (
    <section className="parent-prompt card" aria-label="Which device it came from">
      <p>{PARENT_PROMPT}</p>
      {readOnly ? (
        <SignInLine />
      ) : (
        <>
          {/* no form of its own: the Read a label result shows it inside its form */}
          <div className="row">
            <label>
              <span>Device it came from</span>
              <input
                value={device}
                maxLength={500}
                placeholder="brand, model, what it is"
                onChange={(e) => setDevice(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    onText()
                  }
                }}
              />
            </label>
            <button type="button" disabled={busy || !device.trim()} onClick={onText}>
              Save
            </button>
          </div>
          <div className="row">
            <label>
              <span>Add a photo of the device</span>
              <input type="file" accept="image/*" disabled={busy} onChange={onPhoto} />
            </label>
            <span className="muted">{busy ? 'Reading…' : 'One Muse Spark reading of the label'}</span>
          </div>
        </>
      )}
      {line && <p className="meta">{line}</p>}
    </section>
  )
}
