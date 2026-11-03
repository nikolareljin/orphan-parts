import { expect, test, type APIRequestContext, type Locator } from '@playwright/test'

// The project tests build on items with the names the recorded proposal uses, and the profile
// test writes the same preferences record, so they run one after the other and share nothing
// with the other files.
test.describe.configure({ mode: 'serial' })

const stamp = `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`

// The recorded proposal names items by these names; the ids are whatever the inventory gives.
async function household(request: APIRequestContext): Promise<void> {
  for (const [item_type, name] of [
    ['laptop', 'Old laptop'],
    ['monitor', 'Spare monitor'],
    ['keyboard', 'USB keyboard'],
    ['vacuum', 'Upright vacuum'],
  ]) {
    const res = await request.post('/api/items', { data: { item_type, name, notes: `build ${stamp}` } })
    expect(res.status()).toBe(201)
  }
}

// Select the project; an item still committed to an earlier run's project is moved here.
async function selectAndCommit(panel: Locator): Promise<void> {
  await panel.getByRole('button', { name: 'Select and commit the items' }).click()
  const move = panel.getByRole('button', { name: 'Move it here' })
  await expect(panel.getByText('selected: items committed').or(move)).toBeVisible()
  if (await move.isVisible()) await move.click()
  await expect(panel).toContainText('selected: items committed')
}

test('preferences are kept, proposals come from the inventory, and selection commits the items', async ({ page, request }) => {
  test.slow() // a whole project's life in one run: proposals, selection, the pack, the outcome, the share
  await household(request)
  await page.goto('/')
  await page.getByRole('button', { name: 'Build and reuse' }).click()

  const prefs = page.getByRole('form', { name: 'What I want from a build' })
  await prefs.getByRole('button', { name: 'Edit' }).click()
  await prefs.getByLabel('Interests').fill(`a quiet desk ${stamp}`)
  await prefs.getByLabel('Budget').fill('50')
  await prefs.getByRole('button', { name: 'Save' }).click()
  await expect(prefs).toContainText('saved')

  const propose = page.getByRole('form', { name: 'Propose projects' })
  await expect(propose).toContainText('Homework workstation')
  await propose.getByRole('button', { name: 'Propose' }).click()
  await expect(propose).toContainText(/proposed/)

  const table = page.getByRole('table', { name: 'Projects' })
  await expect(table).toContainText('Homework desk from the old laptop and the spare monitor')
  await expect(table).toContainText('The upright vacuum back to work')

  const panel = page.getByRole('article', { name: /Project Homework desk/ })
  await expect(panel.getByRole('list', { name: 'Items on this project' })).toContainText('Old laptop')
  await expect(panel.getByRole('list', { name: 'Missing requirements' })).toContainText('A cable between the two')
  await expect(panel.getByRole('list', { name: 'Unknowns' })).toContainText('HDMI output')
  await selectAndCommit(panel)
  await expect(panel.getByRole('list', { name: 'Items on this project' })).toContainText('(committed)')
  await expect(page.getByLabel('Budget across selected projects')).toContainText(/\d+ selected, estimated cost \d+ USD of 50 USD/)
  await expect(panel.getByRole('button', { name: 'Start building' })).toBeDisabled()

  // the missing cable becomes a search request on the Find page
  const needed = panel.getByRole('list', { name: 'Missing requirements' })
  await needed.getByRole('button', { name: 'Find it on Marketplace' }).first().click()
  await expect(needed).toContainText('open on Find a part')

  // the cable, bought and saved, fills the requirement from the inventory; the build can start
  const cable = await request.post('/api/items', { data: { item_type: 'HDMI cable', name: `Cable ${stamp}` } })
  expect(cable.status()).toBe(201)
  const cableId = ((await cable.json()) as { id: number }).id
  await panel.getByRole('button', { name: 'Close panel' }).click()
  await page.getByRole('row', { name: /Homework desk/ }).first().getByRole('button', { name: 'Open' }).click()
  const again = page.getByRole('article', { name: /Project Homework desk/ })
  await again.getByRole('combobox', { name: 'Item for A cable between the two (HDMI, DisplayPort or USB-C)' }).selectOption(String(cableId))
  await again.getByRole('list', { name: 'Missing requirements' }).getByRole('button', { name: 'Use it' }).first().click()
  await expect(again.getByRole('list', { name: 'Items on this project' })).toContainText(`Cable ${stamp}`)
  await again.getByRole('button', { name: 'Start building' }).click()
  await expect(again).toContainText('being built')

  // the build pack is written from what stands, with a file to keep; a tick is progress
  await again.getByRole('button', { name: 'Write the build pack' }).click()
  const packs = again.getByRole('list', { name: 'Packs' })
  await expect(packs).toContainText('version 1')
  await expect(packs.getByRole('link', { name: 'Download' })).toHaveAttribute('href', /\/api\/packs\/\d+\.md$/)
  const packUrl = await packs.getByRole('link', { name: 'Download' }).getAttribute('href')
  const file = await request.get(packUrl ?? '')
  expect(file.status()).toBe(200)
  expect(await file.text()).toContain('# Homework desk from the old laptop and the spare monitor')
  await again.getByRole('list', { name: 'Progress' }).getByRole('checkbox').first().check()
  await expect(again).toContainText('1 of 3 steps done')
  await expect(packs).toContainText('out of date')

  // the outcome, in the owner's words: a working result marks it done, and the share text is redacted
  const outcome = again.getByRole('form', { name: 'Record the outcome' })
  await outcome.getByLabel('What was set up').fill('laptop on the monitor over HDMI')
  await outcome.getByLabel('How it was tested').fill('a full homework session')
  await outcome.getByLabel('Limitations').fill('the laptop fan is loud')
  await outcome.getByRole('button', { name: 'Record the outcome' }).click()
  await expect(again).toContainText('done')
  await expect(again.getByLabel('Recorded outcome')).toContainText('working')
  await again.getByLabel(/Share the outcome/).check()
  const share = again.getByRole('textbox', { name: 'Share text' })
  await expect(share).toHaveValue(/Built from: hdmi cable, keyboard, laptop, monitor\./)
  await expect(share).toHaveValue(/a full homework session/)
  await expect(share).toHaveValue(/Homework desk from the laptop and the monitor/)
  await expect(share).not.toHaveValue(/old laptop/i)

  // the project opens in a dialog; the page behind waits until it is closed
  await page.getByRole('dialog').getByRole('button', { name: 'Close', exact: true }).click()
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await page.getByRole('button', { name: 'Find a part' }).click()
  await expect(page.getByRole('table', { name: 'Searches' })).toContainText('A cable between the two')
})

test('an item committed to one build is a conflict for another until it is moved', async ({ page, request }) => {
  await household(request)
  await page.goto('/')
  await page.getByRole('button', { name: 'Build and reuse' }).click()
  const propose = page.getByRole('form', { name: 'Propose projects' })
  await propose.getByRole('button', { name: 'Propose' }).click()
  await expect(propose).toContainText(/proposed/)
  const first = page.getByRole('article', { name: /Project Homework desk/ })
  await selectAndCommit(first)
  await page.getByRole('dialog').getByRole('button', { name: 'Close', exact: true }).click()
  await expect(page.getByRole('dialog')).toHaveCount(0)

  await propose.getByRole('button', { name: 'Propose' }).click()
  await expect(propose).toContainText(/proposed/)
  const second = page.getByRole('article', { name: /Project Homework desk/ })
  await second.getByRole('button', { name: 'Select and commit the items' }).click()
  await expect(second.getByRole('alert')).toContainText('Old laptop is committed to "Homework desk')
  await second.getByRole('button', { name: 'Move it here' }).click()
  await expect(second).toContainText('selected: items committed')
  await second.getByRole('button', { name: 'Abandon' }).click()
  await expect(second).toContainText('abandoned')
})

test('the profile rates the skills, adds one of your own, and the Build page reads it', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: 'Profile', exact: true }).click()
  await expect(page).toHaveURL(/#profile$/)
  const form = page.getByRole('form', { name: 'Profile' })
  const skills = form.getByRole('table', { name: 'Skills' })
  // the ten listed, first and last
  await expect(skills.getByRole('rowheader', { name: 'software', exact: true })).toBeVisible()
  await expect(skills.getByRole('rowheader', { name: 'home repair', exact: true })).toBeVisible()

  await form.getByLabel('electronics and soldering: confident').check()
  await form.getByLabel('software: pro').check()
  await form.getByLabel('plumbing: none').check()
  const own = `bike repair ${stamp}`
  await form.getByLabel('Another skill').fill(own)
  await form.getByLabel('Level').selectOption('some')
  await form.getByRole('button', { name: 'Add skill' }).click()
  await expect(skills.getByRole('rowheader', { name: own })).toBeVisible()
  await form.getByLabel('Tools I have').fill('soldering iron, multimeter')
  await form.getByRole('button', { name: 'Save profile' }).click()
  await expect(form).toContainText('saved')

  await page.reload()
  await expect(form.getByLabel('software: pro')).toBeChecked()
  await expect(form.getByLabel(`${own}: some`)).toBeChecked()
  await expect(form.getByLabel('Tools I have')).toHaveValue('soldering iron, multimeter')

  await page.getByRole('button', { name: 'Build and reuse' }).click()
  const prefs = page.getByRole('form', { name: 'What I want from a build' })
  await prefs.getByRole('button', { name: 'Edit' }).click()
  await expect(prefs).toContainText('software: pro, electronics and soldering: confident')
  await expect(prefs.getByRole('link', { name: 'rate them on your Profile' })).toBeVisible()

  // a skill of your own goes as it came; the listed ones stay
  await prefs.getByRole('link', { name: 'rate them on your Profile' }).click()
  await form.getByRole('button', { name: `Remove ${own}` }).click()
  await form.getByRole('button', { name: 'Save profile' }).click()
  await expect(form).toContainText('saved')
  await expect(skills.getByRole('rowheader', { name: own })).toHaveCount(0)
  await expect(form.getByRole('button', { name: 'Remove software' })).toHaveCount(0)
})

test('a project is drawn only on a click, and the picture is labeled as drawn', async ({ page, request }) => {
  await household(request)
  await page.goto('/')
  await page.getByRole('button', { name: 'Build and reuse' }).click()
  const propose = page.getByRole('form', { name: 'Propose projects' })
  await propose.getByRole('button', { name: 'Propose' }).click()
  await expect(propose).toContainText(/proposed/)
  const panel = page.getByRole('article', { name: /Project Homework desk/ })
  const draw = panel.getByRole('button', { name: /^Draw it: Homework desk/ })
  await expect(draw).toBeEnabled()
  await expect(panel).toContainText('Draw how the finished project could look. One image call.')
  // nothing is drawn when the project opens
  await expect(panel.getByRole('img')).toHaveCount(0)
  await draw.click()
  await expect(panel.getByRole('img', { name: /^Illustrative picture 1: Homework desk/ })).toBeVisible()
  await expect(panel).toContainText('not a photo of a real build')
  await expect(panel).toContainText('recorded answer, nothing spent')
  // kept with the project: open it again and it is there, with no new call
  await panel.getByRole('button', { name: 'Close panel' }).click()
  await page.getByRole('row', { name: /Homework desk/ }).first().getByRole('button', { name: 'Open' }).click()
  const again = page.getByRole('article', { name: /Project Homework desk/ })
  await expect(again.getByRole('img', { name: /^Illustrative picture 1: / })).toBeVisible()
  await expect(again.getByRole('img')).toHaveCount(1)
})

test.describe('the demo visitor', () => {
  test.use({ storageState: { cookies: [], origins: [] } })
  const code = process.env.E2E_ACCESS_CODE ?? ''

  test('reads the homework desk and the profile, with nothing to propose, commit or save', async ({ page, playwright, baseURL }) => {
    test.skip(!code, 'the stack runs without a gate')
    const owner = await playwright.request.newContext({ baseURL })
    expect((await owner.post('/api/access', { data: { code } })).ok()).toBe(true)
    await household(owner)
    const proposed = await owner.post('/api/projects/propose', { data: {} })
    expect(proposed.status()).toBe(201)
    const desk = ((await proposed.json()) as { id: number; title: string; allocations: { item_id: number }[] }[]).find((p) => p.title.startsWith('Homework desk'))
    expect(desk).toBeTruthy()
    // a project is shown to the visitor once every item on it is public
    const shown = [...new Set(desk?.allocations.map((a) => a.item_id) ?? [])]
    for (const id of shown) expect((await owner.post(`/api/items/${id}/public`, { data: { public: true } })).ok()).toBe(true)

    const refused: string[] = []
    page.on('response', (r) => {
      if (r.status() === 403) refused.push(r.url())
    })
    try {
      await page.goto('/')
      await page.getByRole('button', { name: 'Build and reuse' }).click()
      await expect(page.getByRole('form', { name: 'Propose projects' })).toContainText('Homework workstation')
      await expect(page.getByRole('button', { name: 'Propose', exact: true })).toHaveCount(0)
      await expect(page.getByRole('button', { name: 'Edit', exact: true })).toHaveCount(0)
      await expect(page.getByLabel('Budget across selected projects')).toHaveCount(0)
      await page.getByRole('table', { name: 'Projects' }).getByRole('row', { name: new RegExp(`^${desk?.title}`) }).first().getByRole('button', { name: 'Open' }).click()
      const panel = page.getByRole('article', { name: /Project Homework desk/ })
      await expect(panel.getByRole('list', { name: 'Items on this project' })).toContainText('Old laptop')
      await expect(panel.getByRole('list', { name: 'Missing requirements' })).toContainText('A cable between the two')
      for (const name of ['Select and commit the items', 'Shortlist', 'Abandon', 'Find it on Marketplace', 'Write the build pack']) {
        await expect(panel.getByRole('button', { name, exact: true })).toHaveCount(0)
      }
      await expect(panel.getByRole('button', { name: /^Draw (it|again)/ })).toHaveCount(0)
      await expect(panel).toContainText('Sign in with the access code to draw.')
      await expect(panel).toContainText('Sign in with the access code to use this.')
      await expect(panel.locator('input, textarea, select')).toHaveCount(0)
      await page.getByRole('dialog').getByRole('button', { name: 'Close', exact: true }).click()

      // the profile: the skills and their levels, read; nothing to save
      await page.getByRole('button', { name: 'Profile' }).click()
      const skills = page.getByRole('table', { name: 'Skills' })
      await expect(skills.getByRole('row', { name: /electronics and soldering/ })).toBeVisible()
      await expect(skills.getByRole('row', { name: /woodworking/ })).toBeVisible()
      await expect(page.getByRole('button', { name: 'Save profile' })).toHaveCount(0)
      await expect(page.getByRole('radio')).toHaveCount(0)
      await expect(page.getByRole('button', { name: 'Sign in with the code' })).toBeVisible()
      expect(refused).toEqual([])
    } finally {
      for (const id of shown) await owner.post(`/api/items/${id}/public`, { data: { public: false } })
      await owner.dispose()
    }
  })
})
