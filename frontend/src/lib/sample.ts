// The line above a recorded reading shown to the demo visitor (a gated server, no session).
// Every photo gets the answer recorded for a sample, the visitor's own too. Signing in reads
// live only where the server has a key, so the way to a real reading is offered only then.
export const SAMPLE_LINE = 'Recorded answer for a sample photo, not a reading of yours.'
export const SAMPLE_SIGN_IN = ' Sign in with the access code to read your own.'

export function sampleLine(fromFixture: boolean, demo: boolean, liveModels = false): string {
  if (!fromFixture || !demo) return ''
  return liveModels ? SAMPLE_LINE + SAMPLE_SIGN_IN : SAMPLE_LINE
}
