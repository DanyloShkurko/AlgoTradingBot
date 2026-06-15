import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { TrendingUp } from 'lucide-react'
import { useAuth } from '../auth/AuthContext'
import LanguageSwitcher from './LanguageSwitcher'

const inputClass =
  'w-full bg-slate-800 border border-slate-700 rounded-md px-3 py-2 text-sm text-slate-100 focus:outline-none focus:ring-1 focus:ring-emerald-500'

export default function AuthForm({ mode }: { mode: 'login' | 'register' }) {
  const { t } = useTranslation()
  const { login, register } = useAuth()
  const nav = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const isLogin = mode === 'login'

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      if (isLogin) await login(email, password)
      else await register(email, password)
      nav('/bots')
    } catch (err) {
      setError(err instanceof Error ? err.message : t('auth.error'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-950 px-4">
      <div className="w-full max-w-sm">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-2">
            <TrendingUp className="text-emerald-400" size={22} />
            <span className="text-lg font-semibold text-slate-100">AlgoBot</span>
          </div>
          <LanguageSwitcher />
        </div>

        <form onSubmit={submit} className="bg-slate-900 border border-slate-800 rounded-lg p-6 space-y-4">
          <h1 className="text-base font-semibold text-slate-100">
            {isLogin ? t('auth.loginTitle') : t('auth.registerTitle')}
          </h1>

          <div>
            <label className="block text-sm text-slate-400 mb-1">{t('auth.email')}</label>
            <input
              type="email"
              className={inputClass}
              value={email}
              autoComplete="email"
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>

          <div>
            <label className="block text-sm text-slate-400 mb-1">{t('auth.password')}</label>
            <input
              type="password"
              className={inputClass}
              value={password}
              autoComplete={isLogin ? 'current-password' : 'new-password'}
              minLength={6}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
            {!isLogin && <p className="text-xs text-slate-600 mt-1">{t('auth.passwordHint')}</p>}
          </div>

          {error && (
            <div className="text-sm text-red-400 bg-red-900/30 rounded-md px-3 py-2">{error}</div>
          )}

          <button
            type="submit"
            disabled={busy}
            className="w-full bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white font-medium py-2 rounded-md transition-colors text-sm"
          >
            {isLogin ? t('auth.loginButton') : t('auth.registerButton')}
          </button>

          <p className="text-xs text-slate-500 text-center">
            {isLogin ? t('auth.noAccount') : t('auth.haveAccount')}{' '}
            <Link
              to={isLogin ? '/register' : '/login'}
              className="text-emerald-400 hover:text-emerald-300"
            >
              {isLogin ? t('auth.toRegister') : t('auth.toLogin')}
            </Link>
          </p>
        </form>
      </div>
    </div>
  )
}
