export type View = 'read' | 'inbox' | 'inventory' | 'find' | 'build' | 'profile'

export const VIEWS: { id: View; label: string }[] = [
  { id: 'read', label: 'Read a label' },
  { id: 'inbox', label: 'Inbox' },
  { id: 'inventory', label: 'My inventory' },
  { id: 'find', label: 'Find a part' },
  { id: 'build', label: 'Build and reuse' },
  { id: 'profile', label: 'Profile' },
]

// The page lives in the URL hash, so reload and back land where the person was.
export function viewFromHash(hash: string): View {
  const name = hash.replace(/^#/, '').split('/')[0]
  return VIEWS.some((v) => v.id === name) ? (name as View) : 'read'
}

export function hashFor(view: View): string {
  return view === 'read' ? '' : `#${view}`
}
