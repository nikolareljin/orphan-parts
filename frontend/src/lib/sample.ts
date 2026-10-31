// The line at the top of a recorded result shown to the demo visitor (a gated server, no
// session): the answer is the one recorded for the sample, not a reading of anything new.
// Empty otherwise; signed in, the small "recorded answer" badge is enough.
export const SAMPLE_LINE = 'Recorded answer for this sample photo. Sign in with the access code to read your own.'

export function sampleLine(fromFixture: boolean, demo: boolean): string {
  return fromFixture && demo ? SAMPLE_LINE : ''
}
