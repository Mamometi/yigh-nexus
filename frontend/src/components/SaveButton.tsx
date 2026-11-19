import { Link } from 'react-router-dom'
import { useProject, type SavedItem } from '../project'

/** "Add to my project" toggle used on opportunities, faculty and partner organizations. */
export function SaveButton({ item, small }: { item: SavedItem; small?: boolean }) {
  const p = useProject()
  const on = p.has(item.kind, item.id)
  return (
    <span className="save">
      <button type="button" className={`save__btn ${on ? 'is-on' : ''} ${small ? 'save__btn--sm' : ''}`} aria-pressed={on} onClick={() => p.toggle(item)}>
        {on ? '✓ In my project' : '+ Add to my project'}
      </button>
      {on && !small && <Link className="small" to="/launchpad">View my project →</Link>}
    </span>
  )
}
