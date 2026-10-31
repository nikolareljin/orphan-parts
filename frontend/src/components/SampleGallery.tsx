import { api, type SampleCatalog } from '../lib/api'
import { allOfItem, toggleItem, toggleSample } from '../lib/sample'

// The demo set's photos as thumbnails, grouped by item: checkboxes to pick several (and a
// whole item at once), or radio buttons to pick one.
export default function SampleGallery({
  catalog,
  selected,
  onChange,
  multiple = true,
  legend = 'Sample photos',
}: {
  catalog: SampleCatalog
  selected: string[]
  onChange: (next: string[]) => void
  multiple?: boolean
  legend?: string
}) {
  return (
    <fieldset className="sample-gallery">
      <legend>{legend}</legend>
      {catalog.items.map((item) => (
        <div key={item.key} className="sample-item" role="group" aria-label={item.name}>
          <div className="sample-head">
            <strong>{item.name}</strong>
            {multiple && item.photos.length > 1 && (
              <button type="button" className="link" onClick={() => onChange(toggleItem(selected, item))}>
                {allOfItem(selected, item) ? 'Clear the photos of this item' : 'Select all photos of this item'}
              </button>
            )}
          </div>
          <ul className="thumbs">
            {item.photos.map((p, i) => (
              <li key={p.id}>
                <label className="thumb">
                  <input
                    type={multiple ? 'checkbox' : 'radio'}
                    name={multiple ? undefined : 'sample-photo'}
                    checked={selected.includes(p.id)}
                    onChange={() => onChange(multiple ? toggleSample(selected, p.id) : [p.id])}
                  />
                  <img
                    src={api.samples.thumbUrl(p.id)}
                    alt={`${item.name}, photo ${i + 1} of ${item.photos.length}`}
                    loading="lazy"
                  />
                </label>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </fieldset>
  )
}
