import { Link } from 'react-router-dom'
import { matches } from '../api'
import { fmtDate } from './OppCardView'
import { ErrorState, Loading } from './StateViews'
import { useAsync } from '../hooks'

/** Open, priority-aligned opportunities with suggested Yale faculty and potential external partners. */
export function MatchedOpportunities({ limit = 20 }: { limit?: number }) {
  const [state, retry] = useAsync(() => matches.list(limit), [limit])
  return (
    <section className="card matched" aria-labelledby="matched-title">
      <h2 id="matched-title">Open opportunities: suggested faculty and partners</h2>
      <p className="muted small">Open and forecasted opportunities aligned with a YIGH priority, soonest deadline first. Faculty and partner
        organizations are suggestions based on public Yale profiles and past partnerships. Nobody has been contacted.</p>
      {state.status === 'loading' && <Loading label="Matching faculty and partners…" />}
      {state.status === 'error' && <ErrorState message={state.error} onRetry={retry} />}
      {state.status === 'success' && (
        <div className="table-wrap">
          <table className="table matched__table">
            <thead><tr><th>Opportunity</th><th>Funder</th><th>Deadline</th><th>Suggested Yale faculty</th><th>Potential external partners</th></tr></thead>
            <tbody>
              {state.data.opportunities.map(m => (
                <tr key={m.opportunity.id}>
                  <td><Link to={`/radar/${m.opportunity.id}`}>{m.opportunity.title}</Link>
                    <div className="muted small">{m.opportunity.priorities.join(' · ')}</div></td>
                  <td>{m.opportunity.funder ?? '—'}</td>
                  <td>{m.opportunity.deadline ? <>{m.opportunity.status === 'forecasted' ? 'Est. ' : ''}{fmtDate(m.opportunity.deadline)}</>
                       : <span className="muted small">{m.opportunity.deadline_text?.startsWith('No fixed') ? 'No fixed deadline' : m.opportunity.deadline_text ?? 'Not stated'}</span>}</td>
                  <td className="small">{m.top_faculty.map((f, i) => <span key={f.id}>{i > 0 && ', '}<Link to={`/faculty/${f.id}`}>{f.name.split(',')[0]}</Link></span>)}</td>
                  <td className="small">
                    {m.potential_partners.length ? (
                      <ul className="plain matched__partners">
                        {m.potential_partners.map(p => (
                          <li key={p.id}>{p.website ? <a href={p.website} target="_blank" rel="noreferrer">{p.name}</a> : p.name}
                            {p.country && <span className="muted"> ({p.country})</span>}{' '}
                            <span className={`rel rel--${p.relationship}`}>{p.relationship === 'documented' ? 'Connected to Yale' : 'New suggestion'}</span></li>
                        ))}
                      </ul>
                    ) : <span className="muted">{m.partner_gaps[0] ?? 'None suggested'}</span>}
                    <Link to={`/radar/${m.opportunity.id}#partners`} className="matched__more">Details</Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
