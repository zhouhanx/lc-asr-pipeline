import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'

import { AuthProvider } from '@/features/auth/AuthProvider'
import { InitialPasswordPage } from '@/features/auth/InitialPasswordPage'
import { LoginPage } from '@/features/auth/LoginPage'
import { ProtectedRoute } from '@/features/auth/ProtectedRoute'
import { AdminPage } from '@/features/admin/AdminPage'
import { WorkspacePage } from '@/features/workspace/WorkspacePage'

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/change-password" element={<InitialPasswordPage />} />
          <Route path="/admin" element={<AdminPage />} />
          <Route element={<ProtectedRoute />}>
            <Route path="/workspace/*" element={<WorkspacePage />} />
            <Route path="/" element={<Navigate to="/workspace/overview" replace />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}

export default App
