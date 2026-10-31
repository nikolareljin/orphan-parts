import { SIGN_IN_LINE } from '../lib/sample'

// In place of an upload the demo visitor cannot make and has no sample for.
export default function SignInLine({ what }: { what?: string }) {
  return (
    <p className="muted sign-in-line">
      {what && <strong>{what}: </strong>}
      {SIGN_IN_LINE}
    </p>
  )
}
