import type { ReactNode } from 'react'
import { blocks } from '../lib/markdown'

// A build pack, read in place: the plain Markdown the pack is written in (headings, lists,
// numbered steps, paragraphs, **bold**, `code`, [links](https://...) and tables), turned into
// elements. Nothing is set as HTML, so a pack's text can never become markup; a link that is
// not http(s) stays text.

// **bold**, `code` and [text](https://...) inside a line; everything else as it is
function inline(text: string): ReactNode[] {
  const out: ReactNode[] = []
  const re = /\*\*([^*]+)\*\*|`([^`]+)`|\[([^\]]+)\]\(([^)\s]+)\)/g
  let at = 0
  let n = 0
  for (let m = re.exec(text); m; m = re.exec(text)) {
    if (m.index > at) out.push(text.slice(at, m.index))
    if (m[1] !== undefined) out.push(<strong key={n++}>{m[1]}</strong>)
    else if (m[2] !== undefined) out.push(<code key={n++}>{m[2]}</code>)
    else if (/^https?:\/\//.test(m[4])) {
      out.push(
        <a key={n++} href={m[4]} target="_blank" rel="noopener noreferrer">
          {m[3]}
        </a>,
      )
    } else out.push(m[0])
    at = m.index + m[0].length
  }
  if (at < text.length) out.push(text.slice(at))
  return out
}

export default function Markdown({ text, label }: { text: string; label?: string }) {
  return (
    <div className="markdown" aria-label={label}>
      {blocks(text).map((b, i) => {
        if (b.kind === 'heading') {
          // the pack's own title is the section's; its headings sit under the page's
          const level = Math.min(6, b.level + 3)
          const Tag = `h${level}` as 'h4' | 'h5' | 'h6'
          return <Tag key={i}>{inline(b.text)}</Tag>
        }
        if (b.kind === 'list') {
          const items = b.items.map((t, j) => <li key={j}>{inline(t)}</li>)
          return b.ordered ? <ol key={i}>{items}</ol> : <ul key={i}>{items}</ul>
        }
        if (b.kind === 'table') {
          const [head, ...rest] = b.rows
          return (
            <div key={i} className="table-wrap">
              <table className="evidence">
                {head && (
                  <thead>
                    <tr>
                      {head.map((c, j) => (
                        <th key={j} scope="col">
                          {inline(c)}
                        </th>
                      ))}
                    </tr>
                  </thead>
                )}
                <tbody>
                  {rest.map((r, j) => (
                    <tr key={j}>
                      {r.map((c, k) => (
                        <td key={k}>{inline(c)}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        }
        return <p key={i}>{inline(b.text)}</p>
      })}
    </div>
  )
}
