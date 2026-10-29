import { expect, test, type APIRequestContext, type Page } from '@playwright/test'

const stamp = Date.now().toString(36)

async function createItem(
  request: APIRequestContext,
  spec: Record<string, unknown>,
  fields: Record<string, string> = {},
): Promise<number> {
  const res = await request.post('/api/items', { data: spec })
  expect(res.status()).toBe(201)
  const id = ((await res.json()) as { id: number }).id
  for (const [field, value] of Object.entries(fields)) {
    const added = await request.post(`/api/items/${id}/fields`, { data: { field, value } })
    expect(added.status()).toBe(200)
  }
  return id
}

async function openItem(page: Page, name: string) {
  await page.goto('/')
  await page.getByRole('button', { name: 'My inventory' }).click()
  await page.getByRole('table', { name: 'Items' }).getByRole('row', { name }).getByRole('button', { name: 'Open' }).click()
  const panel = page.getByRole('article', { name: `Item ${name}` })
  return { panel, fit: panel.getByRole('region', { name: 'Does it fit?' }) }
}

const laptopNeeds = {
  output_voltage: '19.5',
  output_current: '3.33',
  polarity: 'center positive',
  plug_outer_diameter: '4.5',
  plug_inner_diameter: '3.0',
}

test('an adapter with the wrong voltage is a conflict against the laptop that needs one', async ({ page, request }) => {
  const laptop = `Laptop ${stamp}`
  const laptopId = await createItem(request, { item_type: 'laptop', name: laptop, profile: 'power_adapter' }, laptopNeeds)
  const adapter = `Adapter 12 V ${stamp}`
  await createItem(
    request,
    { item_type: 'power adapter', name: adapter, profile: 'power_adapter' },
    { output_voltage: '12', output_current: '5', polarity: 'center positive', plug_outer_diameter: '4.5', plug_inner_diameter: '3.0' },
  )
  const { fit } = await openItem(page, adapter)
  await fit.getByRole('combobox', { name: 'Needed by' }).selectOption(String(laptopId))
  await fit.getByRole('button', { name: 'Check fit' }).click()

  const status = fit.getByRole('status')
  await expect(status).toContainText('Conflict: does not fit')
  await expect(status).toContainText('a hard rule fails: output voltage')
  const table = status.getByRole('table', { name: 'Checks' })
  await expect(table.getByRole('row', { name: /Output voltage/ })).toContainText('fail')
  await expect(table.getByRole('row', { name: /Output voltage/ })).toContainText('off by 7.5 V')
  await expect(table.getByRole('row', { name: /Polarity/ })).toContainText('pass')
})

test('an adapter that meets every hard rule is compatible, from values written in', async ({ page, request }) => {
  const adapter = `Adapter 19.5 V ${stamp}`
  await createItem(
    request,
    { item_type: 'power adapter', name: adapter, profile: 'power_adapter' },
    { output_voltage: '19.5', output_current: '4.62', polarity: 'centre positive', plug_outer_diameter: '4.5', plug_inner_diameter: '3' },
  )
  const { fit } = await openItem(page, adapter)
  await fit.getByLabel('Output voltage (V)').fill('19.5 V')
  await fit.getByLabel('Output current (A)').fill('3.33')
  await fit.getByLabel('Polarity').fill('center positive')
  await fit.getByLabel('Plug outer diameter (mm)').fill('4.5')
  await fit.getByLabel('Plug inner diameter (mm)').fill('3.0')
  await fit.getByRole('button', { name: 'Check fit' }).click()

  const status = fit.getByRole('status')
  await expect(status).toContainText('Compatible, likely')
  await expect(status).toContainText('every hard rule passes (5)')
  await expect(status.getByRole('table', { name: 'Checks' }).getByRole('row', { name: /Output current/ })).toContainText('pass')
  await expect(status).toContainText('Nothing required for: Part number, Model number, Connector, Plug length')
})

test('a missing polarity leaves the fit open and asks the seller', async ({ page, request }) => {
  const laptop = `Laptop B ${stamp}`
  const laptopId = await createItem(request, { item_type: 'laptop', name: laptop, profile: 'power_adapter' }, laptopNeeds)
  const adapter = `Adapter unmarked ${stamp}`
  await createItem(
    request,
    { item_type: 'power adapter', name: adapter, profile: 'power_adapter' },
    { output_voltage: '19.5', output_current: '3.42', plug_outer_diameter: '4.5', plug_inner_diameter: '3.0' },
  )
  const { fit } = await openItem(page, adapter)
  await fit.getByRole('combobox', { name: 'Needed by' }).selectOption(String(laptopId))
  await fit.getByRole('button', { name: 'Check fit' }).click()

  const status = fit.getByRole('status')
  await expect(status).toContainText('Looks right, evidence missing')
  await expect(status.getByRole('list', { name: 'Questions' })).toContainText('Is the centre of the plug positive or negative?')
  await expect(status.getByRole('table', { name: 'Checks' }).getByRole('row', { name: /Polarity/ })).toContainText('unknown')
})
