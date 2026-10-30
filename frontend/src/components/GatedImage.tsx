import { useEffect, useState } from 'react'
import { mediaUrl } from '../lib/api'

// An <img> for a file behind the gate. Same origin it is a plain image (the cookie goes
// with it); across origins the file is fetched with the session and shown from memory.
export default function GatedImage({ src, alt, loading }: { src: string; alt: string; loading?: 'lazy' | 'eager' }) {
  const [shown, setShown] = useState<string>('')
  useEffect(() => {
    let cancelled = false
    let made = ''
    setShown('')
    mediaUrl(src)
      .then((url) => {
        if (cancelled) {
          if (url !== src) URL.revokeObjectURL(url)
          return
        }
        made = url
        setShown(url)
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
      if (made && made !== src) URL.revokeObjectURL(made)
    }
  }, [src])
  if (!shown) return <span className="image-pending" aria-label={alt} />
  return <img src={shown} alt={alt} loading={loading} />
}
