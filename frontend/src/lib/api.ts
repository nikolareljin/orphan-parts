// All calls to the backend go through here. In dev, Vite proxies these paths to :8000;
// in production the frontend and the API share an origin behind nginx.

export interface Readiness {
  status: 'ok' | 'degraded'
  model_api: 'live' | 'fixture' | 'record'
  data_dir_writable: boolean
  spend_usd: number
  spend_cap_usd: number
  paused: boolean
  demo: {
    gated: boolean
    live_models: boolean
    paused: boolean
    daily_used: number
    daily_cap: number
    visitor_cap_per_hour: number
  }
}

export interface Limits {
  max_clip_mb: number
  max_photos: number
  max_upload_mb: number
}

export interface Version {
  name: string
  version: string
  models: Record<string, string>
  limits: Limits
  // whether the item dialog may draw a picture of what an item could become (PICTURE_ENABLED)
  pictures: boolean
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
  enhanced: boolean
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
  public: boolean
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

// How many photos are kept with an item; each is at /api/items/{id}/photos/{n}, 1 first.
export interface PhotoCount {
  count: number
}

// A picture of what the item could become, drawn by Muse Image on a click and kept beside the
// photos, never as one of them; at /api/items/{id}/pictures/{n}. Illustrative, not evidence.
export interface Picture {
  n: number
  use: string
  model: string
  cost_usd: number
  from_fixture: boolean
  created_at: string
}

export interface PictureList {
  enabled: boolean
  pictures: Picture[]
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

export type DraftMode = 'sell' | 'give'
export type StepGroup = 'prepare' | 'photos' | 'data'

export interface Step {
  key: string
  label: string
  group: StepGroup
  required: boolean
  done: boolean
}

export interface DraftFact {
  text: string
  field: string
}

export interface DraftRequest {
  mode: DraftMode
  holds_data: boolean
  pickup: string
  asking_price: string
}

export interface Draft {
  id: number
  item_id: number
  mode: DraftMode
  version: number
  item_version: number
  stale: boolean
  title: string
  description: string
  facts: DraftFact[]
  uses: string[]
  keywords: string[]
  warnings: string[]
  to_confirm: string[]
  pickup: string
  asking_price: string
  holds_data: boolean
  checklist: Step[]
  ready: boolean
  handoff_url: string
  model: string
  from_fixture: boolean
  cost_usd: number
  at: string
}

export interface VoiceNote {
  transcript: string
  seconds: number
  cut: boolean
  field: string
  model: string
  from_fixture: boolean
  cost_usd: number
  item: Item
}

export type PriceKind = 'asking' | 'sold' | 'reported' | 'estimate'

export interface Comparable {
  kind: 'asking' | 'sold'
  title: string
  price: number
  currency: string
  condition: string
  observed: string
  source_url: string
  source_title: string
}

export interface Quantity {
  kind: PriceKind
  label: string
  count: number
  low: number | null
  high: number | null
  typical: number | null
  currency: string
  basis: string
}

export interface Strategy {
  name: 'quick_sale' | 'typical' | 'patient'
  label: string
  price: number | null
  note: string
}

export interface PartsComparison {
  components: number
  priced: number
  sum_typical: number | null
  whole_typical: number | null
  note: string
}

export interface Guidance {
  id: number
  item_id: number
  version: number
  item_version: number
  stale: boolean
  currency: string
  quantities: Quantity[]
  comparables: Comparable[]
  dropped: number
  sources: { url: string; title: string; observed: string }[]
  estimate_label: 'estimate'
  strategies: Strategy[]
  weak: boolean
  weak_reason: string
  caveats: string[]
  parts: PartsComparison | null
  searches: number
  model: string
  from_fixture: boolean
  cost_usd: number
  at: string
}

export interface PriceRequest {
  currency: string
  country: string
  city: string
}

export interface PriceReport {
  id: number
  item_id: number
  price: number
  currency: string
  sold_on: string
  note: string
  at: string
}

export type SearchStatus = 'open' | 'found' | 'closed'
export type SourceKind = 'text' | 'screenshot' | 'manual'
export type CandidateState = 'unassessed' | 'needs_evidence' | 'conflicting' | 'documented' | 'rejected' | 'withdrawn'

export interface SearchCreate {
  need_item_id: number | null
  profile: string
  title: string
  spec: Record<string, string>
  max_price: number | null
  currency: string
  radius_km: number | null
}

export interface Search {
  id: number
  need_item_id: number | null
  profile: string
  title: string
  spec: Record<string, string>
  radius_km: number | null
  max_price: number | null
  currency: string
  budget_left: number | null
  notes: string
  status: SearchStatus
  handoff_url: string
  candidates: number
  created_at: string
  updated_at: string
}

export interface Candidate {
  id: number
  search_id: number
  source_kind: SourceKind
  observed_on: string
  expires_on: string
  expired: boolean
  asking_price: string
  currency: string
  location: string
  included_parts: string
  url: string
  title: string
  text: string
  note: string
  fields: Record<string, Evidence>
  warnings: string[]
  assessment: Assessment | null
  state: CandidateState
  questions: string[]
  model: string
  from_fixture: boolean
  cost_usd: number
  created_at: string
  assessed_at: string
}

export interface SellerQuestions {
  candidate_id: number
  subject: string
  message: string
  questions: string[]
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

// Build and reuse: what the owner wants, what may be proposed, and projects with their items.
export type Effort = 'low' | 'medium' | 'high'
export type Purchase = 'used' | 'new' | 'either'
export type ProjectStatus = 'proposed' | 'shortlisted' | 'selected' | 'building' | 'done' | 'abandoned'

// The owner's skills, each rated; a record kept before the ratings reads as "some".
export type SkillLevel = 'none' | 'some' | 'confident' | 'pro'

export interface RatedSkill {
  skill: string
  level: SkillLevel
}

export interface Preferences {
  interests: string
  effort: Effort
  skills: RatedSkill[]
  tools: string
  opens_devices: boolean
  budget: number | null
  currency: string
  radius_km: number | null
  purchase: Purchase
}

export interface TemplateSummary {
  id: string
  label: string
  goal: string
  effort: Effort
  requirements: string[]
}

export interface Allocation {
  item_id: number
  item_name: string
  requirement: string
  committed: boolean
  why: string
}

export interface Requirement {
  key: string
  label: string
  kind: 'item' | 'capability'
  blocking: boolean
  state: 'pass' | 'unknown'
  item_id: number | null
  search_id: number | null
  profile: string
}

export interface Outcome {
  configuration: string
  test: string
  tested_on: string
  working: boolean
  limitations: string
  recorded_at: string
  shared: boolean
}

export type OutcomeCreate = Pick<Outcome, 'configuration' | 'test' | 'tested_on' | 'working' | 'limitations'>

export interface Pack {
  id: number
  project_id: number
  version: number
  digest: string
  stale: boolean
  markdown: string
  created_at: string
}

export interface Project {
  id: number
  template: string
  title: string
  status: ProjectStatus
  version: number
  result: string
  requirements: Requirement[]
  allocations: Allocation[]
  effort: Effort
  skills: string[]
  spend_estimate: number
  currency: string
  unknowns: string[]
  sources: string[]
  steps: string[]
  safety: string[]
  dropped: string[]
  progress: boolean[]
  outcome: Outcome | null
  model: string
  from_fixture: boolean
  cost_usd: number
  created_at: string
  updated_at: string
}

export interface Budget {
  budget: number | null
  currency: string
  committed_spend: number
  remaining: number | null
  selected: number
}

export interface ProjectList {
  projects: Project[]
  budget: Budget
}

export interface Conflict {
  item_id: number
  item_name: string
  project_id: number
  project_title: string
}

// Decide what an item becomes: what the rules say it fills, what the model proposes it is good
// for, and one view that gathers what the app already answered about it.
export type DecisionChoice = 'keep_fix' | 'keep_build' | 'sell' | 'give' | 'not_worth'

export interface Use {
  title: string
  what_it_does: string
  needs: string[]
  effort: Effort
  note: string
}

export interface TemplateFit {
  id: string
  label: string
  fills: string[]
}

export interface Uses {
  id: number
  item_id: number
  version: number
  item_version: number
  stale: boolean
  templates: TemplateFit[]
  uses: Use[]
  model: string
  from_fixture: boolean
  cost_usd: number
  at: string
}

// What to do with it, for this owner: three cards written by the model from the item and the
// profile, and the one it recommends.
export type Difficulty = 'easy' | 'moderate' | 'hard'
export type Recommendation = 'keep_fix' | 'reuse' | 'sell' | 'give'

export interface KeepFix {
  worth_fixing: boolean
  problems: string[]
  steps: string[]
  difficulty: Difficulty
  why: string
  parts: string[]
  cost: string
  time: string
}

export interface ReuseScenario {
  title: string
  what_it_does: string
  with_items: string[]
  difficulty: Difficulty
  why: string
  extra_parts: string[]
  cost: string
  time: string
}

export interface SellCard {
  selling_points: string[]
  effort: string
  note: string
}

export interface Scenarios {
  id: number
  item_id: number
  version: number
  item_version: number
  // the item was edited since the cards were written; a decision is no edit
  stale: boolean
  // the keep and fix steps of these cards are in the item's notes
  steps_in_notes: boolean
  // written for the owner's profile; false: for an average person, no profile filled in
  profiled: boolean
  keep_fix: KeepFix
  reuse: ReuseScenario[]
  sell: SellCard
  recommended: Recommendation
  reason: string
  model: string
  from_fixture: boolean
  cost_usd: number
  at: string
}

export interface Worth {
  id: number
  version: number
  currency: string
  typical: number | null
  strategy: Strategy | null
  weak: boolean
  stale: boolean
  at: string
}

export interface OpenSearch {
  id: number
  title: string
  status: SearchStatus
  candidates: number
  handoff_url: string
}

export interface Decided {
  choice: DecisionChoice
  note: string
  at: string
  version: number
}

export interface Decision {
  item: ItemSummary
  accepted_fields: number
  worth: Worth | null
  uses: Uses | null
  scenarios: Scenarios | null
  searches: OpenSearch[]
  templates: TemplateFit[]
  intent: Intent
  // the selected, building or done projects that count on the item, by title
  committed_to: string[]
  last: Decided | null
}

// Captures from the phone: kept as sent, read into an item on request.
export type CaptureStatus = 'received' | 'processed' | 'failed'

export interface Capture {
  id: number
  status: CaptureStatus
  note: string
  name: string
  find_label: boolean
  photos: number
  clip: boolean
  clip_bytes: number
  audio: boolean
  audio_seconds: number
  item_id: number | null
  error: string
  model: string
  cost_usd: number
  created_at: string
  processed_at: string
  public: boolean
}

export interface Access {
  gated: boolean
  granted: boolean
  // whether this caller reaches the live models: the code's door and a key on the host
  live: boolean
  token: string
  expires_at: number
}

// A 401 (the token kept for that session is dropped), or a write refused as the demo visitor,
// means the session is gone: the shell is told, so it shows the way in again.
export const ACCESS_REQUIRED_EVENT = 'opl-access-required'
export const DEMO_PREFIX = 'demo:'
function noteStatus(status: number, detail = ''): void {
  if (status === 401) keepToken('')
  const lost = status === 401 || (status === 403 && detail.startsWith(DEMO_PREFIX))
  if (lost && typeof window !== 'undefined') window.dispatchEvent(new Event(ACCESS_REQUIRED_EVENT))
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
    readonly body: unknown = undefined,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

export const apiBase = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, '') ?? ''

export function apiUrl(path: string): string {
  return `${apiBase}${path.startsWith('/') ? path : `/${path}`}`
}

// When the API lives on another origin (the web app on Cloudflare Pages, the backend on
// Modal), the gate's cookie never crosses, so the session token from POST /api/access is
// kept for the tab and sent as a bearer header. Same origin keeps the cookie and no token.
const TOKEN_KEY = 'opl-session'
export const crossOrigin = apiBase !== '' && (typeof window === 'undefined' || !apiBase.startsWith(window.location.origin))

export function keepToken(token: string): void {
  if (!crossOrigin) return
  try {
    if (token) sessionStorage.setItem(TOKEN_KEY, token)
    else sessionStorage.removeItem(TOKEN_KEY)
  } catch {
    // storage blocked: the session lasts the page
  }
}

function authHeaders(): Record<string, string> {
  if (!crossOrigin) return {}
  try {
    const token = sessionStorage.getItem(TOKEN_KEY)
    return token ? { Authorization: `Bearer ${token}` } : {}
  } catch {
    return {}
  }
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(apiUrl(path), { headers: { Accept: 'application/json', ...authHeaders() }, credentials: 'include' })
  if (!res.ok) {
    const detail = await detailOf(res, path)
    noteStatus(res.status, detail)
    throw new ApiError(res.status, detail)
  }
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
  const res = await fetch(apiUrl(path), { method: 'POST', body: form, headers: { Accept: 'application/json', ...authHeaders() }, credentials: 'include' })
  if (!res.ok) {
    const detail = await detailOf(res, path)
    noteStatus(res.status, detail)
    throw new ApiError(res.status, detail)
  }
  return (await res.json()) as T
}

async function sendJson<T>(method: 'POST' | 'PUT' | 'PATCH' | 'DELETE', path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json', ...authHeaders() }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  const res = await fetch(apiUrl(path), { method, headers, body: body === undefined ? undefined : JSON.stringify(body), credentials: 'include' })
  if (!res.ok) {
    const answer = res.clone()
    const detail = await detailOf(res, path)
    noteStatus(res.status, detail)
    throw new ApiError(res.status, detail, await answer.json().catch(() => undefined))
  }
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

// An image or a clip behind the gate: same origin the browser's cookie goes with the <img>;
// across origins the file is fetched with the bearer header and handed over as an object
// URL, which the caller revokes when done.
export async function mediaUrl(url: string): Promise<string> {
  if (!crossOrigin) return url
  const res = await fetch(url, { headers: authHeaders(), credentials: 'include' })
  if (!res.ok) {
    noteStatus(res.status)
    throw new ApiError(res.status, `${url}: HTTP ${res.status}`)
  }
  return URL.createObjectURL(await res.blob())
}

export const api = {
  access: {
    status: () => getJson<Access>('/api/access'),
    grant: async (code: string) => {
      const access = await sendJson<Access>('POST', '/api/access', { code })
      keepToken(access.granted ? access.token : '')
      return access
    },
    // the browser forgets the session either way: a DELETE that never arrives still ends it here
    leave: async () => {
      try {
        return await sendJson<Access>('DELETE', '/api/access')
      } finally {
        keepToken('')
      }
    },
  },
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
    setPublic: (id: number, isPublic: boolean) => sendJson<Item>('POST', `/api/items/${id}/public`, { public: isPublic }),
    addField: (id: number, spec: FieldCreate) => sendJson<Item>('POST', `/api/items/${id}/fields`, spec),
    review: (id: number, assertionId: number, review: Review) =>
      sendJson<Item>('POST', `/api/items/${id}/assertions/${assertionId}/review`, { review }),
    addComponent: (id: number, spec: ComponentCreate) => sendJson<Item>('POST', `/api/items/${id}/components`, spec),
    events: (id: number) => getJson<ItemEvent[]>(`/api/items/${id}/events`),
    photos: (id: number) => getJson<PhotoCount>(`/api/items/${id}/photos`),
    photoUrl: (id: number, n: number) => apiUrl(`/api/items/${id}/photos/${n}`),
    pictures: (id: number) => getJson<PictureList>(`/api/items/${id}/pictures`),
    drawPicture: (id: number, use: string) => sendJson<Picture>('POST', `/api/items/${id}/picture`, { use }),
    pictureUrl: (id: number, n: number) => apiUrl(`/api/items/${id}/pictures/${n}`),
    addPhotos: (id: number, photos: File[]) =>
      postForm<PhotoCount>(
        `/api/items/${id}/photos`,
        photos.map((p): FormPart => ['uploads', p]),
      ),
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
  drafts: {
    list: (itemId: number) => getJson<Draft[]>(`/api/items/${itemId}/drafts`),
    write: (itemId: number, request: DraftRequest) => sendJson<Draft>('POST', `/api/items/${itemId}/drafts`, request),
    get: (id: number) => getJson<Draft>(`/api/drafts/${id}`),
    setStep: (id: number, key: string, done: boolean) => sendJson<Draft>('POST', `/api/drafts/${id}/checklist`, { key, done }),
  },
  voice: (itemId: number, audio: File) => postForm<VoiceNote>(`/api/items/${itemId}/voice`, [['audio', audio]]),
  value: {
    guide: (itemId: number, request: PriceRequest) => sendJson<Guidance>('POST', `/api/items/${itemId}/price`, request),
    history: (itemId: number) => getJson<Guidance[]>(`/api/items/${itemId}/price`),
    report: (itemId: number, spec: { price: number; currency: string; sold_on: string; note: string }) =>
      sendJson<PriceReport>('POST', `/api/items/${itemId}/price/reports`, spec),
    reports: (itemId: number) => getJson<PriceReport[]>(`/api/items/${itemId}/price/reports`),
  },
  assess: (need: Side, candidate: Side) => sendJson<Assessment>('POST', '/api/assess', { need, candidate }),
  find: {
    searches: () => getJson<Search[]>('/api/searches'),
    create: (spec: SearchCreate) => sendJson<Search>('POST', '/api/searches', spec),
    get: (id: number) => getJson<Search>(`/api/searches/${id}`),
    patch: (id: number, patch: { status?: SearchStatus; notes?: string }) => sendJson<Search>('PATCH', `/api/searches/${id}`, patch),
    candidates: (id: number) => getJson<Candidate[]>(`/api/searches/${id}/candidates`),
    addCandidate: (id: number, request: Record<string, unknown>, screenshot: File | null) =>
      postForm<Candidate>(`/api/searches/${id}/candidates`, [
        ['request', JSON.stringify(request)],
        ...(screenshot ? ([['screenshot', screenshot]] as FormPart[]) : []),
      ]),
    candidate: (id: number) => getJson<Candidate>(`/api/candidates/${id}`),
    recheck: (id: number) => sendJson<Candidate>('POST', `/api/candidates/${id}/recheck`),
    withdraw: (id: number) => sendJson<Candidate>('POST', `/api/candidates/${id}/withdraw`),
    questions: (id: number) => getJson<SellerQuestions>(`/api/candidates/${id}/questions`),
  },
  build: {
    preferences: () => getJson<Preferences>('/api/preferences'),
    setPreferences: (prefs: Preferences) => sendJson<Preferences>('PUT', '/api/preferences', prefs),
    templates: () => getJson<TemplateSummary[]>('/api/templates'),
    propose: (count: number, note: string) => sendJson<Project[]>('POST', '/api/projects/propose', { count, note }),
    projects: () => getJson<ProjectList>('/api/projects'),
    project: (id: number) => getJson<Project>(`/api/projects/${id}`),
    shortlist: (id: number) => sendJson<Project>('POST', `/api/projects/${id}/shortlist`),
    select: (id: number, take = false) => sendJson<Project>('POST', `/api/projects/${id}/select`, { take }),
    abandon: (id: number) => sendJson<Project>('POST', `/api/projects/${id}/abandon`),
    advance: (id: number, to: 'building' | 'done') => sendJson<Project>('POST', `/api/projects/${id}/advance/${to}`),
    searchFor: (id: number, key: string) => sendJson<Project>('POST', `/api/projects/${id}/requirements/${key}/search`),
    fill: (id: number, key: string, itemId: number) =>
      sendJson<Project>('POST', `/api/projects/${id}/requirements/${key}/fill`, { item_id: itemId, why: '' }),
    writePack: (id: number) => sendJson<Pack>('POST', `/api/projects/${id}/pack`),
    packs: (id: number) => getJson<Pack[]>(`/api/projects/${id}/packs`),
    packUrl: (packId: number) => apiUrl(`/api/packs/${packId}.md`),
    setProgress: (id: number, step: number, done: boolean) => sendJson<Project>('POST', `/api/projects/${id}/progress`, { step, done }),
    recordOutcome: (id: number, outcome: OutcomeCreate) => sendJson<Project>('POST', `/api/projects/${id}/outcome`, outcome),
    setShared: (id: number, shared: boolean) => sendJson<Project>('POST', `/api/projects/${id}/outcome/share`, { shared }),
    shareText: (id: number) => getJson<{ text: string }>(`/api/projects/${id}/outcome/share`),
    // how the finished project could look, drawn by Muse Image on a click; kept with the project
    pictures: (id: number) => getJson<PictureList>(`/api/projects/${id}/pictures`),
    drawPicture: (id: number) => sendJson<Picture>('POST', `/api/projects/${id}/picture`),
    pictureUrl: (id: number, n: number) => apiUrl(`/api/projects/${id}/pictures/${n}`),
  },
  decide: {
    view: (itemId: number) => getJson<Decision>(`/api/items/${itemId}/decide`),
    uses: (itemId: number) => sendJson<Uses>('POST', `/api/items/${itemId}/uses`),
    scenarios: (itemId: number) => sendJson<Scenarios>('POST', `/api/items/${itemId}/scenarios`),
    // made from the item version the panel showed: a stale choice is refused with 409
    choose: (itemId: number, choice: DecisionChoice, note: string, version?: number) =>
      sendJson<Item>('POST', `/api/items/${itemId}/decision`, { choice, note, version }),
    // how a reuse card's project could look, drawn on a click; kept with the card (from 0)
    cardPictures: (itemId: number, scenariosId: number, card: number) =>
      getJson<PictureList>(`/api/items/${itemId}/scenarios/${scenariosId}/reuse/${card}/pictures`),
    drawCard: (itemId: number, scenariosId: number, card: number) =>
      sendJson<Picture>('POST', `/api/items/${itemId}/scenarios/${scenariosId}/reuse/${card}/picture`),
    cardPictureUrl: (itemId: number, scenariosId: number, card: number, n: number) =>
      apiUrl(`/api/items/${itemId}/scenarios/${scenariosId}/reuse/${card}/pictures/${n}`),
  },
  pair: {
    // the phone talks to the API's own origin when the web app is served elsewhere; the door
    // the page is at goes in too, so the image of one door is never shown for the other
    svgUrl: (origin: string, door = '') =>
      apiUrl(
        `/api/pair.svg?origin=${encodeURIComponent(origin)}${apiBase ? `&api=${encodeURIComponent(apiBase)}` : ''}${door ? `&door=${door}` : ''}`,
      ),
    // the image, when the pairing in it ends (Unix seconds; 0 when it carries none) and how
    // many seconds it has left by the server's clock (null when not said). The Referer goes
    // along whatever the page's own policy: the server draws only an origin it is reached at
    svg: async (origin: string, door = '') => {
      const res = await fetch(api.pair.svgUrl(origin, door), {
        headers: authHeaders(),
        credentials: 'include',
        referrerPolicy: 'same-origin',
      })
      if (!res.ok) {
        noteStatus(res.status)
        throw new ApiError(res.status, `pair.svg: HTTP ${res.status}`)
      }
      const left = res.headers.get('X-Pair-Expires-In')
      return {
        svg: await res.text(),
        expiresAt: Number(res.headers.get('X-Pair-Expires-At') ?? 0) || 0,
        expiresIn: left !== null && Number.isFinite(Number(left)) ? Number(left) : null,
      }
    },
    get: (origin: string) =>
      getJson<{ url: string; gated: boolean; token: string; expires_at: number }>(
        `/api/pair?origin=${encodeURIComponent(origin)}${apiBase ? `&api=${encodeURIComponent(apiBase)}` : ''}`,
      ),
  },
  captures: {
    list: () => getJson<{ captures: Capture[] }>('/api/captures'),
    // the bundle the phone sends, from this computer: photos, one clip, a name and a line
    send: (photos: File[], clip: File | null, request: { name: string; note: string }) =>
      postForm<Capture>('/api/captures', [
        ...photos.map((p): FormPart => ['photos', p]),
        ...(clip ? [['clip', clip] as FormPart] : []),
        ['request', JSON.stringify({ ...request, find_label: true })],
      ]),
    get: (id: number) => getJson<Capture>(`/api/captures/${id}`),
    process: (id: number) => sendJson<Capture>('POST', `/api/captures/${id}/process`),
    remove: (id: number) => sendJson<void>('DELETE', `/api/captures/${id}`),
    setPublic: (id: number, isPublic: boolean) => sendJson<Capture>('POST', `/api/captures/${id}/public`, { public: isPublic }),
    photoUrl: (id: number, n: number) => apiUrl(`/api/captures/${id}/photos/${n}`),
    clipUrl: (id: number) => apiUrl(`/api/captures/${id}/clip`),
    noteUrl: (id: number) => apiUrl(`/api/captures/${id}/note`),
  },
  measure: (photo: File, request: MeasureRequest) =>
    postForm<MeasureResult>('/api/measure', [
      ['photo', photo],
      ['request', JSON.stringify(request)],
    ]),
}
