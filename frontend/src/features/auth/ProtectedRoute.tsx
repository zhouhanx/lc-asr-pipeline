import { Navigate, Outlet, useLocation } from 'react-router-dom'

import { useAuth } from './useAuth'

export function ProtectedRoute() {
  const location = useLocation()
  const { loading, session } = useAuth()

  if (loading) {
    return (
      <main className="pixel-grid grid min-h-screen place-items-center p-6">
        <div className="border-2 border-border bg-primary px-6 py-4 font-mono text-sm shadow-md">
          SESSION CHECK...
        </div>
      </main>
    )
  }
  if (!session) return <Navigate to="/login" replace state={{ from: location }} />
  return <Outlet />
}
