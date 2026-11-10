import { expect, test, type APIRequestContext, type Page } from '@playwright/test'
import { SIGNED_OUT } from '../global-setup'

const stamp = `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`
const code = process.env.E2E_ACCESS_CODE ?? ''

async function createLaptop(request: APIRequestContext, name: string): Promise<number> {
  const res = await request.post('/api/items', { data: { item_type: 'laptop', name, condition: 'scuffed lid' } })
  expect(res.status()).toBe(201)
  const id = ((await res.json()) as { id: number }).id
  expect((await request.post(`/api/items/${id}/fields`, { data: { field: 'ram', value: '8', unit: 'GB' } })).status()).toBe(200)
  return id
}

async function openItem(page: Page, name: string) {
  await page.goto('/')
  await page.getByRole('button', { name: 'My inventory' }).click()
  await page.getByRole('table', { name: 'Items' }).getByRole('row', { name }).getByRole('button', { name: 'Open' }).click()
  const panel = page.getByRole('article', { name: `Item ${name}` })
  return {
    panel,
    drawn: panel.getByRole('region', { name: 'What it could look like' }),
    cards: panel.getByRole('region', { name: 'Decide' }).getByRole('region', { name: 'What to do with it' }),
  }
}

test('the owner likes a drawing and dislikes a set of cards with a reason; both stay after a reload', async ({ page, request }) => {
  test.slow()
  const name = `Voted laptop ${stamp}`
  await createLaptop(request, name)
  const { drawn, cards } = await openItem(page, name)

  await drawn.getByLabel('Draw it as').fill('a bedside lamp')
  await drawn.getByRole('button', { name: 'Draw it' }).click()
  await expect(drawn.getByRole('img', { name: 'Illustrative picture 1: a bedside lamp' })).toBeVisible()
  const like = drawn.getByRole('button', { name: 'Like this drawing', exact: true })
  await expect(like).toHaveAttribute('aria-pressed', 'false')
  await like.click()
  await expect(like).toHaveAttribute('aria-pressed', 'true')
  await expect(like).toContainText('1')

  await cards.getByRole('button', { name: 'What should I do with it?' }).click()
  const vote = cards.getByRole('group', { name: 'Your vote on this set of cards' })
  const dislike = vote.getByRole('button', { name: 'Dislike this set of cards', exact: true })
  await dislike.click()
  await expect(dislike).toHaveAttribute('aria-pressed', 'true')
  // a dislike asks what is wrong, in one optional line
  await vote.getByLabel("What's wrong?").fill('the reuse card needs a monitor I do not own')
  await vote.getByRole('button', { name: 'Save' }).click()
  await expect(vote).toContainText('the reuse card needs a monitor I do not own')
  await expect(vote.getByLabel("What's wrong?")).toHaveCount(0)

  await page.reload()
  const again = await openItem(page, name)
  const liked = again.drawn.getByRole('button', { name: 'Like this drawing', exact: true })
  await expect(liked).toHaveAttribute('aria-pressed', 'true')
  await expect(liked).toContainText('1')
  const kept = again.cards.getByRole('group', { name: 'Your vote on this set of cards' })
  await expect(kept.getByRole('button', { name: 'Dislike this set of cards', exact: true })).toHaveAttribute('aria-pressed', 'true')
  await expect(kept).toContainText('the reuse card needs a monitor I do not own')

  // a second click takes the like back
  await liked.click()
  await expect(liked).toHaveAttribute('aria-pressed', 'false')
  await expect(liked).toContainText('0')
})

test('a slow vote shows pressed at once, is sent once, and the late first read does not undo it', async ({ page, request }) => {
  test.slow()
  const name = `Slow voted laptop ${stamp}`
  const id = await createLaptop(request, name)
  expect((await request.post(`/api/items/${id}/picture`, { data: { use: 'a bedside lamp' } })).status()).toBe(201)
  const mine = (url: URL) => url.pathname === '/api/feedback' && url.searchParams.get('target_id') === String(id)
  // the first read of the tally answers late, after the vote is saved; the vote itself is slow
  let reads = 0
  await page.route(mine, async (route) => {
    reads += 1
    if (reads === 1) await new Promise((r) => setTimeout(r, 4000))
    await route.continue()
  })
  let posts = 0
  let release: () => void = () => {}
  const held = new Promise<void>((r) => (release = r))
  await page.route('**/api/feedback', async (route) => {
    if (route.request().method() !== 'POST') return route.fallback()
    posts += 1
    await held
    await route.continue()
  })
  const firstRead = page.waitForResponse((r) => mine(new URL(r.url())) && r.request().method() === 'GET')
  const { drawn } = await openItem(page, name)
  const group = drawn.getByRole('group', { name: 'Your vote on this drawing' })
  const like = group.getByRole('button', { name: 'Like this drawing', exact: true })
  await like.click()
  // pressed at once, while the request is on its way; nothing can be sent twice
  await expect(like).toHaveAttribute('aria-pressed', 'true')
  await expect(group).toHaveAttribute('aria-busy', 'true')
  await expect(like).toBeDisabled()
  await like.click({ force: true })
  const saved = page.waitForResponse((r) => r.url().includes('/api/feedback') && r.request().method() === 'POST')
  release()
  expect((await saved).status()).toBe(200)
  await firstRead
  await expect(group).toHaveAttribute('aria-busy', 'false')
  await expect(like).toHaveAttribute('aria-pressed', 'true')
  await expect(like).toContainText('1')
  expect(posts).toBe(1)
  // and the server has it
  const target = new URLSearchParams({ target_kind: 'item_picture', target_id: String(id), target_ref: '1' })
  expect(((await (await request.get(`/api/feedback?${target.toString()}`)).json()) as { mine: string | null }).mine).toBe('like')
})

test('a vote the server never answers is put back as the server has it, with the error shown', async ({ page, request }) => {
  const name = `Failed vote laptop ${stamp}`
  const id = await createLaptop(request, name)
  expect((await request.post(`/api/items/${id}/picture`, { data: { use: 'a bedside lamp' } })).status()).toBe(201)
  await page.route('**/api/feedback', (route) => (route.request().method() === 'POST' ? route.abort('failed') : route.fallback()))
  const { drawn } = await openItem(page, name)
  const group = drawn.getByRole('group', { name: 'Your vote on this drawing' })
  const dislike = group.getByRole('button', { name: 'Dislike this drawing', exact: true })
  await dislike.click()
  await expect(group.getByRole('alert')).toBeVisible()
  await expect(dislike).toHaveAttribute('aria-pressed', 'false')
  await expect(dislike).toContainText('0')
  await expect(dislike).toBeEnabled()
})

test.describe('the demo visitor', () => {
  test.use({ storageState: SIGNED_OUT })

  test('sees the drawing but no vote buttons, and cannot read or cast a vote', async ({ page, playwright, baseURL }) => {
    test.skip(!code, 'the stack runs without a gate')
    const owner = await playwright.request.newContext({ baseURL })
    expect((await owner.post('/api/access', { data: { code } })).ok()).toBe(true)
    const name = `Public voted laptop ${stamp}`
    const id = await createLaptop(owner, name)
    expect((await owner.post(`/api/items/${id}/picture`, { data: { use: 'a bedside lamp' } })).status()).toBe(201)
    const target = { target_kind: 'item_picture', target_id: id, target_ref: '1' }
    const cast = await owner.post('/api/feedback', { data: { ...target, vote: 'dislike', reason: 'the owner only' } })
    expect(cast.status()).toBe(200)
    expect((await owner.post(`/api/items/${id}/public`, { data: { public: true } })).ok()).toBe(true)
    try {
      const query = new URLSearchParams({ ...target, target_id: String(id) }).toString()
      const read = await page.request.get(`/api/feedback?${query}`)
      expect(read.status()).toBe(403)
      expect(await read.text()).not.toContain('the owner only')
      expect((await page.request.post('/api/feedback', { data: { ...target, vote: 'like' } })).status()).toBe(403)

      const { drawn } = await openItem(page, name)
      await expect(drawn.getByRole('img', { name: 'Illustrative picture 1: a bedside lamp' })).toBeVisible()
      await expect(drawn.getByRole('button', { name: /^(Like|Dislike) this drawing$/ })).toHaveCount(0)
      await expect(page.getByRole('group', { name: /^Your vote on/ })).toHaveCount(0)
    } finally {
      await owner.delete(`/api/items/${id}`)
      await owner.dispose()
    }
  })
})

test('a judge votes on the demo set under its own code; the owner counts it', async ({ browser, request }) => {
  const judgeCode = process.env.E2E_JUDGE_CODE ?? ''
  test.skip(!judgeCode, 'no judge code was issued for this run')
  const name = `Judged laptop ${stamp}`
  const id = await createLaptop(request, name)
  expect((await request.post(`/api/items/${id}/picture`, { data: { use: 'a bedside lamp' } })).status()).toBe(201)
  expect((await request.post(`/api/items/${id}/public`, { data: { public: true } })).ok()).toBe(true)
  const target = { target_kind: 'item_picture', target_id: String(id), target_ref: '1' }

  const context = await browser.newContext({ storageState: SIGNED_OUT })
  const page = await context.newPage()
  try {
    expect((await page.request.post('/api/access', { data: { code: judgeCode } })).ok()).toBe(true)
    const { drawn } = await openItem(page, name)
    const like = drawn.getByRole('button', { name: 'Like this drawing', exact: true })
    await like.click()
    await expect(like).toHaveAttribute('aria-pressed', 'true')
    await expect(like).toContainText('1')
  } finally {
    await context.close()
  }
  // the owner counts the judge's like, which is not the owner's own vote
  const seen = (await (await request.get(`/api/feedback?${new URLSearchParams(target).toString()}`)).json()) as { likes: number; mine: string | null }
  expect(seen.likes).toBeGreaterThanOrEqual(1)
  expect(seen.mine).toBeNull()
})
