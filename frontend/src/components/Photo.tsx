import { useState } from 'react'

/** Faculty headshot from their public Yale profile; a generic profile silhouette when there is none (or it fails to load). */
export function Photo({ src, name, className = '' }: { src?: string | null; name: string; className?: string }) {
  const [failed, setFailed] = useState(false)
  if (src && !failed) return <img className={`photo ${className}`} src={src} alt={`Photo of ${name}`} loading="lazy" onError={() => setFailed(true)} />
  return (
    <svg className={`photo photo--generic ${className}`} viewBox="0 0 100 100" role="img" aria-label={`No photo available for ${name}`}>
      <rect width="100" height="100" fill="#dde4ee" />
      <circle cx="50" cy="40" r="17" fill="#9fb0c6" />
      <path d="M18 100c0-19 14-32 32-32s32 13 32 32z" fill="#9fb0c6" />
    </svg>
  )
}
