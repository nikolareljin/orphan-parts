import { mkdirSync, writeFileSync } from 'node:fs'
import { request, type FullConfig } from '@playwright/test'

// One session through the gate before the shots, with the throwaway code the generator started
// its stack with (SHOTS_ACCESS_CODE, never typed into a page that is shot): every guide starts
// signed in from its cookie, on localhost and on the stack's private address (the pairing
// shots); the visitor's shots start from no cookie at all.
export const STATE_FILE = `${process.env.SHOTS_OUT ?? 'out'}/.auth/state.json`

export default async function setup(config: FullConfig): Promise<void> {
  const code = process.env.SHOTS_ACCESS_CODE ?? ''
  mkdirSync(STATE_FILE.replace(/\/[^/]+$/, ''), { recursive: true })
  const cookies: unknown[] = []
  const bases = [config.projects[0]?.use.baseURL ?? 'http://localhost:5173', process.env.SHOTS_LAN_URL].filter(Boolean) as string[]
  for (const baseURL of bases) {
    const context = await request.newContext({ baseURL })
    const status = (await (await context.get('/api/access')).json()) as { gated: boolean }
    if (status.gated) {
      if (!code) throw new Error('the stack is gated but SHOTS_ACCESS_CODE is empty')
      const res = await context.post('/api/access', { data: { code } })
      if (!res.ok()) throw new Error(`the access code was refused: HTTP ${res.status()}`)
    }
    cookies.push(...(await context.storageState()).cookies)
    await context.dispose()
  }
  writeFileSync(STATE_FILE, JSON.stringify({ cookies, origins: [] }))
}
