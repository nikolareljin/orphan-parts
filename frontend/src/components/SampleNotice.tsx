import { sampleLine } from '../lib/sample'

// A plain line at the top of a recorded result while signed out, so a sample answer is never
// taken for a reading of a photo of your own.
export default function SampleNotice({ fromFixture, demo }: { fromFixture: boolean; demo: boolean }) {
  const text = sampleLine(fromFixture, demo)
  if (!text) return null
  return (
    <p className="hint sample" role="note">
      {text}
    </p>
  )
}
