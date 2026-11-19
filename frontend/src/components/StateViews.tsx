import { useEffect, useState, type ReactNode } from 'react'

export function Loading({ label = 'Loading…' }: { label?: string }) {
  // the free server sleeps when idle; if loading drags on, say so instead of looking broken
  const [slow, setSlow] = useState(false)
  useEffect(() => { const t = setTimeout(() => setSlow(true), 5000); return () => clearTimeout(t) }, [])
  return (
    <div className="state" role="status" aria-live="polite">
      <div className="spinner" aria-hidden />
      <p>{label}</p>
      {slow && <p className="state__slow small">Still working. If nobody has used the site for a while, the server takes up to a minute to wake up. Thanks for waiting.</p>}
    </div>
  )
}

export function EmptyState({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="state state--empty" role="status">
      <div className="state__icon" aria-hidden>✦</div>
      <h3>{title}</h3>
      {children && <p>{children}</p>}
      {action}
    </div>
  )
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="state state--error" role="alert">
      <div className="state__icon" aria-hidden>!</div>
      <h3>Something went wrong</h3>
      <p>{message}</p>
      {onRetry && <button className="btn" onClick={onRetry}>Try again</button>}
    </div>
  )
}

/** Placeholder shapes shown while a page's code loads: the layout appears at once instead of a spinner. */
export function PageSkeleton() {
  return (
    <div className="skel" aria-busy="true" aria-label="Loading page">
      <div className="skel__bar skel__bar--title" />
      <div className="skel__bar skel__bar--line" />
      <div className="skel__grid">{[0, 1, 2, 3, 4, 5].map(i => <div key={i} className="skel__card" />)}</div>
    </div>
  )
}
