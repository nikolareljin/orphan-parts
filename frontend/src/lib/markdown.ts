// The plain Markdown a build pack is written in, as blocks: headings, lists, numbered steps,
// tables and paragraphs. Read by the Markdown component; nothing here is ever HTML.

export type Block =
  | { kind: 'heading'; level: number; text: string }
  | { kind: 'list'; ordered: boolean; items: string[] }
  | { kind: 'table'; rows: string[][] }
  | { kind: 'paragraph'; text: string }

export function blocks(markdown: string): Block[] {
  const out: Block[] = []
  const lines = markdown.replace(/\r\n?/g, '\n').split('\n')
  let i = 0
  while (i < lines.length) {
    const line = lines[i]
    const heading = /^(#{1,6})\s+(.*)$/.exec(line)
    if (heading) {
      out.push({ kind: 'heading', level: heading[1].length, text: heading[2].trim() })
      i++
      continue
    }
    const bullet = /^\s*[-*]\s+(.*)$/.exec(line)
    const numbered = /^\s*\d+[.)]\s+(.*)$/.exec(line)
    if (bullet || numbered) {
      const ordered = !bullet
      const items: string[] = []
      while (i < lines.length) {
        const m = ordered ? /^\s*\d+[.)]\s+(.*)$/.exec(lines[i]) : /^\s*[-*]\s+(.*)$/.exec(lines[i])
        if (!m) break
        items.push(m[1])
        i++
      }
      out.push({ kind: 'list', ordered, items })
      continue
    }
    if (/^\s*\|.*\|\s*$/.test(line)) {
      const rows: string[][] = []
      while (i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i])) {
        const cells = lines[i].trim().slice(1, -1).split('|').map((c) => c.trim())
        // the line under the header (|---|---|) only shapes the table
        if (!cells.every((c) => /^:?-{3,}:?$/.test(c))) rows.push(cells)
        i++
      }
      out.push({ kind: 'table', rows })
      continue
    }
    if (line.trim() === '') {
      i++
      continue
    }
    const text: string[] = []
    while (i < lines.length && lines[i].trim() !== '' && !/^(#{1,6})\s|^\s*([-*]|\d+[.)])\s|^\s*\|/.test(lines[i])) {
      text.push(lines[i].trim())
      i++
    }
    out.push({ kind: 'paragraph', text: text.join(' ') })
  }
  return out
}
