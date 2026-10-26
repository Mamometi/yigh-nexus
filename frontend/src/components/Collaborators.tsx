import { useState } from 'react'
import { api } from '../api'
import { useAsync } from '../hooks'
import { ConstellationGraph } from './ConstellationGraph'
import { MatchCard } from './MatchCard'
import { EmptyState, ErrorState, Loading } from './StateViews'

export function Collaborators({ facultyId, name }: { facultyId: number; name: string }) {
  const [crossSchool, setCrossSchool] = useState(false)
  const [newOnly, setNewOnly] = useState(false)
  const [state, retry] = useAsync(
    () => api.collaborators(facultyId, { limit: 12, cross_school_only: crossSchool, new_connections_only: newOnly }),
    [facultyId, crossSchool, newOnly])

  return (
    <section className="collab" id="collaborators" aria-labelledby="collab-title">
      <div className="collab__head">
        <div>
          <h2 id="collab-title">Suggested collaborators</h2>
          <p className="muted">Ranked by how well their research fits with {name.split(',')[0]}’s: shared topics, complementary skills, places and YIGH priorities.</p>
        </div>
        <div className="toggles">
          <label className="toggle">
            <input type="checkbox" checked={newOnly} onChange={e => setNewOnly(e.target.checked)} />
            <span>New connections only (hide existing co-authors)</span>
          </label>
          <label className="toggle">
            <input type="checkbox" checked={crossSchool} onChange={e => setCrossSchool(e.target.checked)} />
            <span>Only show people in other schools</span>
          </label>
        </div>
      </div>

      {state.status === 'loading' && <Loading label="Finding collaborators…" />}
      {state.status === 'error' && <ErrorState message={state.error} onRetry={retry} />}
      {state.status === 'success' && state.data.matches.length === 0 && (
        <EmptyState title="No strong suggestions yet">
          {crossSchool || newOnly ? 'No matches with these options. Try turning a filter off.'
            : 'This profile doesn’t say enough about their research to suggest collaborators. Adding a fuller bio or research interests to the Yale profile would help.'}
        </EmptyState>
      )}
      {state.status === 'success' && state.data.matches.length > 0 && (
        <>
          <ConstellationGraph center={name} matches={state.data.matches} />
          <p className="disclaimer small">ⓘ {state.data.disclaimer}</p>
          <ol className="match-list">
            {state.data.matches.map(m => <li key={m.faculty.id}><MatchCard m={m} selfName={name} /></li>)}
          </ol>
        </>
      )}
    </section>
  )
}
