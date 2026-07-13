import { type ReactNode } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { useAuth } from './auth/AuthContext'
import Layout from './components/Layout'
import Login from './pages/Login'
import Register from './pages/Register'
import Bots from './pages/Bots'
import CreateBot from './pages/CreateBot'
import EditBot from './pages/EditBot'
import BotDetail from './pages/BotDetail'
import Accounts from './pages/Accounts'

function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) {
    return <div className="min-h-screen flex items-center justify-center text-slate-600">…</div>
  }
  if (!user) return <Navigate to="/login" replace />
  return <>{children}</>
}

function PublicOnly({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) return null
  if (user) return <Navigate to="/bots" replace />
  return <>{children}</>
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<PublicOnly><Login /></PublicOnly>} />
        <Route path="/register" element={<PublicOnly><Register /></PublicOnly>} />
        <Route element={<RequireAuth><Layout /></RequireAuth>}>
          <Route path="/" element={<Navigate to="/bots" replace />} />
          <Route path="/bots" element={<Bots />} />
          <Route path="/bots/new" element={<CreateBot />} />
          <Route path="/bots/:id/edit" element={<EditBot />} />
          <Route path="/bots/:id" element={<BotDetail />} />
          <Route path="/accounts" element={<Accounts />} />
        </Route>
        <Route path="*" element={<Navigate to="/bots" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
