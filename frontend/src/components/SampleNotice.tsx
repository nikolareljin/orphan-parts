import { sampleLine } from '../lib/sample'

// A plain line above a recorded reading while signed out, so a sample answer is never taken
// for a reading of the visitor's own photo.
export default function SampleNotice({ fromFixture, demo, liveModels }: { fromFixture: boolean; demo: boolean; liveModels: boolean }) {
  const text = sampleLine(fromFixture, demo, liveModels)
  if (!text) return null
  return (
    <p className="hint sample" role="note">
      {text}
    </p>
  )
}
