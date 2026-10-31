import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, api, apiUrl, dataUrlToFile } from './api'

describe('apiUrl', () => {
  it('keeps same-origin paths relative when no base is set', () => {
    expect(apiUrl('/healthz')).toBe('/healthz')
  })

  it('adds a leading slash', () => {
    expect(apiUrl('api/version')).toBe('/api/version')
  })
})

describe('dataUrlToFile', () => {
  it('decodes the base64 body and keeps the mime type', async () => {
    const file = dataUrlToFile('data:image/jpeg;base64,AAE=', 'crop.jpg')
    expect(file.name).toBe('crop.jpg')
    expect(file.type).toBe('image/jpeg')
    expect(new Uint8Array(await file.arrayBuffer())).toEqual(new Uint8Array([0, 1]))
  })
})

describe('api', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('reads readiness from /readyz', async () => {
    const fetchMock = vi.fn<typeof fetch>(async () => Response.json({ status: 'ok' }))
    vi.stubGlobal('fetch', fetchMock)
    await api.readiness()
    expect(fetchMock).toHaveBeenCalledWith('/readyz', { headers: { Accept: 'application/json' }, credentials: 'include' })
  })

  it('reads version from /api/version', async () => {
    const fetchMock = vi.fn<typeof fetch>(async () => Response.json({ name: 'orphan-parts' }))
    vi.stubGlobal('fetch', fetchMock)
    await api.version()
    expect(fetchMock).toHaveBeenCalledWith('/api/version', { headers: { Accept: 'application/json' }, credentials: 'include' })
  })

  it('reports the path and status on failure', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>(async () => new Response('boom', { status: 503 })),
    )
    await expect(api.readiness()).rejects.toThrow('/readyz: HTTP 503')
  })

  it('posts every photo as multipart under the photos field', async () => {
    const fetchMock = vi.fn<typeof fetch>(async () => Response.json({ item_type: 'adapter', fields: {} }))
    vi.stubGlobal('fetch', fetchMock)
    const a = new File([new Uint8Array([1, 2, 3])], 'a.jpg', { type: 'image/jpeg' })
    const b = new File([new Uint8Array([4])], 'b.png', { type: 'image/png' })

    const result = await api.extract([a, b])

    expect(result.item_type).toBe('adapter')
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/extract')
    expect(init?.method).toBe('POST')
    const form = init?.body as FormData
    const names = form.getAll('photos').map((f) => (f as File).name)
    expect(names).toEqual(['a.jpg', 'b.png'])
    expect(form.getAll('crops')).toEqual([])
  })

  it('posts label crops under the crops field', async () => {
    const fetchMock = vi.fn<typeof fetch>(async () => Response.json({ item_type: 'adapter', fields: {} }))
    vi.stubGlobal('fetch', fetchMock)
    const photo = new File([new Uint8Array([1])], 'a.jpg', { type: 'image/jpeg' })
    const crop = new File([new Uint8Array([2])], 'label-1.jpg', { type: 'image/jpeg' })

    await api.extract([photo], [crop])

    const form = fetchMock.mock.calls[0][1]?.body as FormData
    expect(form.getAll('photos').map((f) => (f as File).name)).toEqual(['a.jpg'])
    expect(form.getAll('crops').map((f) => (f as File).name)).toEqual(['label-1.jpg'])
  })

  it('posts one photo and the concepts to /api/segment', async () => {
    const fetchMock = vi.fn<typeof fetch>(async () => Response.json({ regions: [], overlay: '' }))
    vi.stubGlobal('fetch', fetchMock)
    const photo = new File([new Uint8Array([1])], 'a.jpg', { type: 'image/jpeg' })

    await api.segment(photo, ['label', 'opening'])

    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/segment')
    const form = init?.body as FormData
    expect((form.get('photo') as File).name).toBe('a.jpg')
    expect(form.getAll('concepts')).toEqual(['label', 'opening'])
  })

  it('surfaces the API detail text on a 400', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>(async () => Response.json({ detail: 'the file is not an image' }, { status: 400 })),
    )
    const err = await api.extract([new File(['x'], 'notes.txt')]).catch((e: unknown) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect((err as ApiError).status).toBe(400)
    expect((err as ApiError).message).toBe('the file is not an image')
  })

  it('joins the messages of a validation error', async () => {
    const detail = [
      { loc: ['body', 'photos'], msg: 'Field required', type: 'missing' },
      { loc: ['body', 'other'], msg: 'Extra inputs are not permitted', type: 'extra_forbidden' },
    ]
    vi.stubGlobal('fetch', vi.fn<typeof fetch>(async () => Response.json({ detail }, { status: 422 })))
    await expect(api.extract([])).rejects.toThrow('Field required; Extra inputs are not permitted')
  })

  it('posts an item as JSON and reads the answer', async () => {
    const fetchMock = vi.fn<typeof fetch>(async () => Response.json({ id: 7, name: 'adapter' }, { status: 201 }))
    vi.stubGlobal('fetch', fetchMock)
    const item = await api.items.create({ item_type: 'adapter', intent: 'sell' })
    expect(item.id).toBe(7)
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/items')
    expect(init?.method).toBe('POST')
    expect((init?.headers as Record<string, string>)['Content-Type']).toBe('application/json')
    expect(JSON.parse(init?.body as string)).toEqual({ item_type: 'adapter', intent: 'sell' })
  })

  it('patches with the version and reviews an assertion', async () => {
    const fetchMock = vi.fn<typeof fetch>(async () => Response.json({ id: 7 }))
    vi.stubGlobal('fetch', fetchMock)
    await api.items.update(7, { intent: 'give', version: 3 })
    await api.items.review(7, 12, 'accepted')
    expect(fetchMock.mock.calls[0][0]).toBe('/api/items/7')
    expect(fetchMock.mock.calls[0][1]?.method).toBe('PATCH')
    expect(fetchMock.mock.calls[1][0]).toBe('/api/items/7/assertions/12/review')
    expect(JSON.parse(fetchMock.mock.calls[1][1]?.body as string)).toEqual({ review: 'accepted' })
  })

  it('treats a 204 on delete as done', async () => {
    vi.stubGlobal('fetch', vi.fn<typeof fetch>(async () => new Response(null, { status: 204 })))
    await expect(api.items.remove(7)).resolves.toBeUndefined()
  })

  it('surfaces a version conflict as the API message', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>(async () => Response.json({ detail: 'item 7 is at version 2, not 1' }, { status: 409 })),
    )
    const err = await api.items.update(7, { intent: 'give', version: 1 }).catch((e: unknown) => e)
    expect((err as ApiError).status).toBe(409)
    expect((err as ApiError).message).toBe('item 7 is at version 2, not 1')
  })

  it('falls back to the status when the error body is not JSON', async () => {
    vi.stubGlobal('fetch', vi.fn<typeof fetch>(async () => new Response('<html>', { status: 502 })))
    await expect(api.extract([new File(['x'], 'a.jpg')])).rejects.toThrow('/api/extract: HTTP 502')
  })
})

describe('api.pair.svgUrl', () => {
  it('names the door, so a sign-in draws the code again', () => {
    const origin = 'http://192.168.1.20:5173'
    expect(api.pair.svgUrl(origin)).toBe(`/api/pair.svg?origin=${encodeURIComponent(origin)}`)
    expect(api.pair.svgUrl(origin, 'demo')).not.toBe(api.pair.svgUrl(origin, 'in'))
    expect(api.pair.svgUrl(origin, 'in')).toContain('&door=in')
  })
})

describe('api.pair.svg', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('reads the pairing end and the seconds it has left off the image', async () => {
    const headers = { 'X-Pair-Expires-At': '1800000000', 'X-Pair-Expires-In': '900' }
    vi.stubGlobal('fetch', vi.fn<typeof fetch>(async () => new Response('<svg/>', { headers })))
    expect(await api.pair.svg('http://192.168.1.20:5173', 'in')).toEqual({ svg: '<svg/>', expiresAt: 1800000000, expiresIn: 900 })
  })

  it('says null for the seconds left when the server does not say them', async () => {
    vi.stubGlobal('fetch', vi.fn<typeof fetch>(async () => new Response('<svg/>')))
    expect(await api.pair.svg('http://192.168.1.20:5173')).toEqual({ svg: '<svg/>', expiresAt: 0, expiresIn: null })
  })
})
