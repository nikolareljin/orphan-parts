import type { Draft, DraftMode, Step, StepGroup } from './api'

export const MODES: { value: DraftMode; label: string }[] = [
  { value: 'sell', label: 'Sell' },
  { value: 'give', label: 'Give away' },
]

export function modeLabel(mode: DraftMode): string {
  return MODES.find((m) => m.value === mode)?.label ?? mode
}

export function groupLabel(group: StepGroup): string {
  switch (group) {
    case 'prepare':
      return 'Before handing it over'
    case 'photos':
      return 'Photos'
    case 'data':
      return 'Wipe your data'
  }
}

// Steps in their groups, in the order the groups are meant to be done.
export function stepsByGroup(steps: Step[]): [StepGroup, Step[]][] {
  const order: StepGroup[] = ['prepare', 'photos', 'data']
  return order.map((g): [StepGroup, Step[]] => [g, steps.filter((s) => s.group === g)]).filter(([, list]) => list.length > 0)
}

// What goes to the clipboard: the title, a blank line, the text as it would be posted.
export function draftText(draft: Draft): string {
  return `${draft.title}\n\n${draft.description}`
}

export function remaining(steps: Step[]): number {
  return steps.filter((s) => s.required && !s.done).length
}
