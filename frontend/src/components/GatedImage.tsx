import { useEffect, useState } from 'react'
import { mediaUrl } from '../lib/api'

// An <img> for a file behind the gate. Same origin it is a plain image (the cookie goes
// with it); across origins the file is fetched with the session and shown from memory.
export default function GatedImage({ src, alt, loading }: { src: string; alt: string; loading?: 'lazy' | 'eager' }) {
  const [shown, setShown] = useState<string>('')
  const [failed, setFailed] = useState(false)
  useEffect(() => {
    let cancelled = false
    let made = ''
    setShown('')
    setFailed(false)
    mediaUrl(src)
      .then((url) => {
        if (cancelled) {
          if (url !== src) URL.revokeObjectURL(url)
          return
        }
        made = url
        setShown(url)
      })
      .catch(() => {
        if (!cancelled) setFailed(true)
      })
    return () => {
      cancelled = true
      if (made && made !== src) URL.revokeObjectURL(made)
    }
  }, [src])
  // not there (gone meanwhile, or the session ended): a marked tile, as a broken image would be
  if (failed) return <span className="image-pending failed" role="img" aria-label={`${alt} (not available)`} />
  if (!shown) return <span className="image-pending" aria-label={alt} />
  return <img src={shown} alt={alt} loading={loading} />
}
