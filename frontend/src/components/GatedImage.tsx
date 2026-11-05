import { useGatedUrl } from '../lib/useGatedUrl'

// An <img> for a file behind the gate.
export default function GatedImage({ src, alt, loading }: { src: string; alt: string; loading?: 'lazy' | 'eager' }) {
  const { shown, failed } = useGatedUrl(src)
  // not there (gone meanwhile, or the session ended): a marked tile, as a broken image would be
  if (failed) return <span className="image-pending failed" role="img" aria-label={`${alt} (not available)`} />
  if (!shown) return <span className="image-pending" aria-label={alt} />
  return <img src={shown} alt={alt} loading={loading} />
}
