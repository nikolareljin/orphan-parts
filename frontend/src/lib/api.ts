// All calls to the backend go through here. In dev, Vite proxies these paths to :8000;
// in production the frontend and the API share an origin behind nginx.

export interface Readiness {
  status: 'ok' | 'degraded'
  model_api: 'live' | 'fixture' | 'record'
  data_dir_writable: boolean
  spend_usd: number
  spend_cap_usd: number
  paused: boolean
}

export interface Limits {
  max_photos: number
  max_upload_mb: number
}

export interface Version {
  name: string
  version: string
  models: Record<string, string>
  limits: Limits
}

export type Source =
  | 'photo'
  | 'label_crop'
  | 'grounding_citation'
  | 'voice_note'
  | 'user_edit'
  | 'video_frame'
  | 'measurement'
  | 'document'

export interface Evidence {
  value: string
  unit: string
  confidence: number
  source: Source
  raw: string
}

export interface Extraction {
  item_type: string
  label_text: string
  fields: Record<string, Evidence>
  warnings: string[]
  photos: number
  crops: number
  model: string
  from_fixture: boolean
  cost_usd: number
}

export interface Box {
  left: number
  top: number
  right: number
  bottom: number
}

export interface Region {
  concept: string
  phrase: string
  object_id: string
  box: Box
  confidence: number | null
  coverage: number
  crop: string
  svg_path: string
}

export interface Segmentation {
  width: number
  height: number
  regions: Region[]
  overlay: string
  warnings: string[]
  model: string
  from_fixture: boolean
  cost_usd: number
}

// Inventory: how a value is known, what the owner means to do, whether a plan may count on it.
export type Provenance = 'observed' | 'owner_reported' | 'documented' | 'tested' | 'estimated'
export type Intent = 'keep' | 'build' | 'sell' | 'give'
export type Availability = 'available' | 'reserved' | 'gone'
export type Review = 'proposed' | 'accepted' | 'rejected'

export interface Assertion {
  id: number
  field: string
  value: string
  unit: string
  provenance: Provenance
  confidence: number
  source: Source
  raw: string
  review: Review
  at: string
}

export interface ItemSummary {
  id: number
  name: string
  item_type: string
  profile: string
  condition: string
  intent: Intent
  availability: Availability
  parent_id: number | null
  field_count: number
  version: number
  updated_at: string
}

export interface Item extends ItemSummary {
  faults: string
  tests_done: string
  accessories: string
  location: string
  notes: string
  created_at: string
  fields: Record<string, Assertion>
  assertions: Assertion[]
  components: number[]
}

export type ItemDetails = Pick<
  Item,
  | 'name'
  | 'item_type'
  | 'profile'
  | 'condition'
  | 'faults'
  | 'tests_done'
  | 'accessories'
  | 'location'
  | 'notes'
  | 'intent'
  | 'availability'
>

export interface ItemCreate extends Partial<ItemDetails> {
  extraction?: Extraction
  parent_id?: number | null
}

export type ItemPatch = Partial<ItemDetails> & { version?: number }

export interface FieldCreate {
  field: string
  value: string
  unit?: string
  provenance?: Provenance
  raw?: string
}

export interface ComponentCreate {
  name: string
  item_type?: string
  condition?: string
  notes?: string
}

export interface ItemEvent {
  id: number
  item_id: number
  at: string
  actor: string
  change: string
  version: number
}

// Profiles and measurements: what to measure for a kind of item, and a number from a photo.
export interface ProfileSummary {
  id: string
  label: string
  feature_count: number
  rule_count: number
}

export type RuleKind = 'equal' | 'within' | 'at_least' | 'at_most'

export interface ProfileRule {
  key: string
  label: string
  kind: RuleKind
  unit: string
  hard: boolean
  identity: boolean
  tolerance: number | null
  tolerance_pct: number | null
  question: string
}

export type CheckStatus = 'pass' | 'fail' | 'unknown'
export type Verdict = 'EXACT_MATCH' | 'COMPATIBLE_LIKELY' | 'VISUALLY_SIMILAR' | 'CONFLICT' | 'INSUFFICIENT_INFO'

export interface Side {
  item_id?: number
  values?: Record<string, string>
  profile?: string
}

export interface Backing {
  provenance: Provenance
  review: Review
  source: string
  uncertainty: number | null
  at: string
}

export interface Check {
  key: string
  label: string
  kind: RuleKind
  hard: boolean
  identity: boolean
  status: CheckStatus
  needed: string
  observed: string
  unit: string
  basis: string
  backing: Backing | null
}

export interface Assessment {
  profile: string
  verdict: Verdict
  summary: string
  checks: Check[]
  questions: string[]
  missing: string[]
  to_confirm: string[]
  need_item: number | null
  candidate_item: number | null
}

export interface ProfileFeature {
  key: string
  label: string
  unit: string
  tolerance_mm: number
  how: string
}

export interface Point {
  x: number
  y: number
}

export type Reference =
  | { kind: 'two_point'; points: Point[]; length_mm: number; tolerance_mm?: number }
  | { kind: 'rectangle'; corners: Point[]; width_mm: number; height_mm: number; tolerance_mm?: number }

export interface MeasureRequest {
  feature: string
  profile: string | null
  image: { width: number; height: number }
  reference: Reference
  points: Point[]
  straight_on: boolean
}

export interface Check {
  name: string
  passed: boolean
  detail: string
  blocking: boolean
}

export interface MeasureResult {
  accepted: boolean
  feature: string
  profile: string | null
  method: 'two_point_scale' | 'homography'
  unit: 'mm'
  value_mm: number | null
  uncertainty_mm: number | null
  basis: string
  checks: Check[]
  redo: string | null
  px_per_mm: number | null
  image: { width: number; height: number }
  reference: Reference
  points: Point[]
  tolerance_mm: number | null
  needs_direct_reading: boolean | null
}

export interface Measurement extends MeasureResult {
  id: number
  item_id: number
  assertion_id: number | null
  at: string
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

export const apiBase = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, '') ?? ''

export function apiUrl(path: string): string {
  return `${apiBase}${path.startsWith('/') ? path : `/${path}`}`
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(apiUrl(path), { headers: { Accept: 'application/json' } })
  if (!res.ok) throw new ApiError(res.status, `${path}: HTTP ${res.status}`)
  return (await res.json()) as T
}

// The backend answers errors as {"detail": "..."}; the text is written to be shown. A request
// the backend could not parse (422) carries one {loc, msg} per problem instead.
async function detailOf(res: Response, path: string): Promise<string> {
  try {
    const body = (await res.json()) as { detail?: unknown }
    if (typeof body.detail === 'string') return body.detail
    if (Array.isArray(body.detail)) {
      const messages = body.detail
        .map((problem) => (problem as { msg?: unknown }).msg)
        .filter((msg): msg is string => typeof msg === 'string')
      if (messages.length > 0) return messages.join('; ')
    }
  } catch {
    // not JSON: fall through to the generic message
  }
  return `${path}: HTTP ${res.status}`
}

export type FormPart = [field: string, value: File | string]

async function postForm<T>(path: string, parts: FormPart[]): Promise<T> {
  const form = new FormData()
  for (const [field, value] of parts) {
    if (typeof value === 'string') form.append(field, value)
    else form.append(field, value, value.name)
  }
  const res = await fetch(apiUrl(path), { method: 'POST', body: form, headers: { Accept: 'application/json' } })
  if (!res.ok) throw new ApiError(res.status, await detailOf(res, path))
  return (await res.json()) as T
}

async function sendJson<T>(method: 'POST' | 'PATCH' | 'DELETE', path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  const res = await fetch(apiUrl(path), { method, headers, body: body === undefined ? undefined : JSON.stringify(body) })
  if (!res.ok) throw new ApiError(res.status, await detailOf(res, path))
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

// A data URL from the API back into a File the API can take as an upload.
export function dataUrlToFile(dataUrl: string, name: string): File {
  const comma = dataUrl.indexOf(',')
  const mime = /^data:([^;]+);base64$/.exec(dataUrl.slice(0, comma))?.[1] ?? 'application/octet-stream'
  const binary = atob(dataUrl.slice(comma + 1))
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)
  return new File([bytes], name, { type: mime })
}

export const api = {
  readiness: () => getJson<Readiness>('/readyz'),
  version: () => getJson<Version>('/api/version'),
  extract: (photos: File[], crops: File[] = []) =>
    postForm<Extraction>('/api/extract', [
      ...photos.map((p): FormPart => ['photos', p]),
      ...crops.map((c): FormPart => ['crops', c]),
    ]),
  segment: (photo: File, concepts: string[] = []) =>
    postForm<Segmentation>('/api/segment', [['photo', photo], ...concepts.map((c): FormPart => ['concepts', c])]),
  items: {
    list: () => getJson<ItemSummary[]>('/api/items'),
    get: (id: number) => getJson<Item>(`/api/items/${id}`),
    create: (spec: ItemCreate) => sendJson<Item>('POST', '/api/items', spec),
    update: (id: number, patch: ItemPatch) => sendJson<Item>('PATCH', `/api/items/${id}`, patch),
    remove: (id: number) => sendJson<void>('DELETE', `/api/items/${id}`),
    addField: (id: number, spec: FieldCreate) => sendJson<Item>('POST', `/api/items/${id}/fields`, spec),
    review: (id: number, assertionId: number, review: Review) =>
      sendJson<Item>('POST', `/api/items/${id}/assertions/${assertionId}/review`, { review }),
    addComponent: (id: number, spec: ComponentCreate) => sendJson<Item>('POST', `/api/items/${id}/components`, spec),
    events: (id: number) => getJson<ItemEvent[]>(`/api/items/${id}/events`),
    measurements: (id: number) => getJson<Measurement[]>(`/api/items/${id}/measurements`),
    measure: (id: number, photo: File, request: MeasureRequest) =>
      postForm<Measurement>(`/api/items/${id}/measurements`, [
        ['photo', photo],
        ['request', JSON.stringify(request)],
      ]),
  },
  profiles: {
    list: () => getJson<ProfileSummary[]>('/api/profiles'),
    features: (id: string) => getJson<ProfileFeature[]>(`/api/profiles/${id}/features`),
    rules: (id: string) => getJson<ProfileRule[]>(`/api/profiles/${id}/rules`),
  },
  assess: (need: Side, candidate: Side) => sendJson<Assessment>('POST', '/api/assess', { need, candidate }),
  measure: (photo: File, request: MeasureRequest) =>
    postForm<MeasureResult>('/api/measure', [
      ['photo', photo],
      ['request', JSON.stringify(request)],
    ]),
}
