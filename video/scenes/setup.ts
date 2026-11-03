import { mkdirSync } from 'node:fs'
import { request, type FullConfig } from '@playwright/test'

// One session through the gate before the scenes, with the throwaway code the generator started
// its stack with (SCENES_ACCESS_CODE, never typed on camera); every scene starts signed in from
// its cookie, the visitor's scene signs out on camera.
export const STATE_FILE = `${process.env.SCENES_OUT ?? 'out'}/.auth/state.json`

export default async function setup(config: FullConfig): Promise<void> {
  const baseURL = config.projects[0]?.use.baseURL ?? 'http://localhost:5173'
  const code = process.env.SCENES_ACCESS_CODE ?? ''
  mkdirSync(STATE_FILE.replace(/\/[^/]+$/, ''), { recursive: true })
  const context = await request.newContext({ baseURL })
  const status = (await (await context.get('/api/access')).json()) as { gated: boolean }
  if (status.gated) {
    if (!code) throw new Error('the stack is gated but SCENES_ACCESS_CODE is empty')
    const res = await context.post('/api/access', { data: { code } })
    if (!res.ok()) throw new Error(`the access code was refused: HTTP ${res.status()}`)
  }
  await context.storageState({ path: STATE_FILE })
  await context.dispose()
}
