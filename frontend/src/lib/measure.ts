import type { MeasureRequest, MeasureResult, Point, Reference } from './api'

export type ReferenceKind = 'two_point' | 'rectangle'

// How many marks each step needs, in order: the reference first, then the feature's two ends.
export function marksNeeded(kind: ReferenceKind): number {
  return (kind === 'two_point' ? 2 : 4) + 2
}

// The label of the next mark to place: R1, R2 (or C1 to C4), then F1, F2.
export function markLabel(index: number, kind: ReferenceKind): string {
  const refCount = kind === 'two_point' ? 2 : 4
  if (index < refCount) return `${kind === 'two_point' ? 'R' : 'C'}${index + 1}`
  return `F${index - refCount + 1}`
}

// The feature to start from when the profile changes: its first one, else a key of your own.
export function defaultFeatureKey(features: { key: string }[]): string {
  return features[0]?.key ?? '__other'
}

export function nextInstruction(count: number, kind: ReferenceKind): string {
  const refCount = kind === 'two_point' ? 2 : 4
  if (count < refCount) {
    return kind === 'two_point'
      ? `Mark end ${count + 1} of the known length on the reference`
      : `Mark corner ${count + 1} of the rectangle (top-left, top-right, bottom-right, bottom-left)`
  }
  if (count < refCount + 2) return `Mark end ${count - refCount + 1} of the feature`
  return 'All marks placed'
}

// The canvas is drawn at most this wide; marks are scaled back to the photo's own pixels.
export function fitScale(naturalWidth: number, maxWidth: number): number {
  return naturalWidth > maxWidth ? maxWidth / naturalWidth : 1
}

export function toPhoto(p: Point, scale: number): Point {
  return { x: p.x / scale, y: p.y / scale }
}

export interface ReferenceSpec {
  kind: ReferenceKind
  length_mm: number
  width_mm: number
  height_mm: number
  tolerance_mm: number
}

// Build the request once every mark is placed; null until then.
export function buildRequest(
  marks: Point[],
  spec: ReferenceSpec,
  feature: string,
  profile: string | null,
  image: { width: number; height: number },
  straightOn: boolean,
): MeasureRequest | null {
  if (marks.length < marksNeeded(spec.kind)) return null
  const refCount = spec.kind === 'two_point' ? 2 : 4
  const reference: Reference =
    spec.kind === 'two_point'
      ? { kind: 'two_point', points: marks.slice(0, 2), length_mm: spec.length_mm, tolerance_mm: spec.tolerance_mm }
      : {
          kind: 'rectangle',
          corners: marks.slice(0, 4),
          width_mm: spec.width_mm,
          height_mm: spec.height_mm,
          tolerance_mm: spec.tolerance_mm,
        }
  return { feature, profile, image, reference, points: marks.slice(refCount, refCount + 2), straight_on: straightOn }
}

export function formatMm(result: Pick<MeasureResult, 'value_mm' | 'uncertainty_mm'>): string {
  if (result.value_mm === null || result.uncertainty_mm === null) return 'no number'
  return `${result.value_mm.toFixed(1)} ± ${result.uncertainty_mm.toFixed(2)} mm`
}

export function methodLabel(method: MeasureResult['method']): string {
  return method === 'two_point_scale' ? 'two-point scale' : 'perspective-corrected from a known rectangle'
}
