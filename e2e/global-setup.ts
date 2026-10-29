import { mkdirSync, writeFileSync } from 'node:fs'
import { request, type FullConfig } from '@playwright/test'

// The dev stack runs behind the demo gate during the browser checks. One session is opened
// here with the code the stack was started with, and every test starts from its cookie; the
// gate itself is checked by tests/access.spec.ts, which starts without one.
export const STATE_FILE = '.auth/state.json'

export default async function globalSetup(config: FullConfig): Promise<void> {
  const baseURL = config.projects[0]?.use.baseURL ?? process.env.E2E_BASE_URL ?? 'http://localhost:5173'
  const code = process.env.E2E_ACCESS_CODE ?? ''
  mkdirSync('.auth', { recursive: true })
  const context = await request.newContext({ baseURL })
  const status = (await (await context.get('/api/access')).json()) as { gated: boolean }
  if (status.gated) {
    if (!code) throw new Error('the stack is gated but E2E_ACCESS_CODE is empty')
    const res = await context.post('/api/access', { data: { code } })
    if (!res.ok()) throw new Error(`the access code was refused: HTTP ${res.status()}`)
  }
  await context.storageState({ path: STATE_FILE })
  await context.dispose()
  writeFileSync('.auth/gated', status.gated ? '1' : '0')
}
