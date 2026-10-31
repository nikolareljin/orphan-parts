import { expect, test, type APIRequestContext, type Locator } from '@playwright/test'

// Both tests build on items with the names the recorded proposal uses, so they run one after
// the other and share nothing with the other files.
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
