import { useEffect, useState } from 'react'
import { mediaUrl } from './api'

// A file behind the gate as a URL an element can show. Same origin it is the plain URL (the
// cookie goes with it); across origins the file is fetched with the session and shown from
// memory, revoked when the element goes.
export function useGatedUrl(src: string): { shown: string; failed: boolean } {
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
  return { shown, failed }
}
