import { NavLink } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Bot as BotIcon, KeyRound, LogOut, TrendingUp } from 'lucide-react'
import { useAuth } from '../auth/AuthContext'
import LanguageSwitcher from './LanguageSwitcher'

const links = [
  { to: '/bots', icon: BotIcon, key: 'bots' },
  { to: '/accounts', icon: KeyRound, key: 'accounts' },
] as const

export default function Sidebar() {
  const { t } = useTranslation()
  const { user, logout } = useAuth()

  return (
    <div className="w-52 shrink-0 bg-slate-900 border-r border-slate-800 flex flex-col">
      <div className="p-4 border-b border-slate-800 flex items-center gap-2">
        <TrendingUp className="text-emerald-400" size={20} />
        <span className="font-semibold text-slate-100">AlgoBot</span>
      </div>

      <nav className="flex-1 p-3 space-y-1">
        {links.map(({ to, icon: Icon, key }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors ${
                isActive
                  ? 'bg-slate-700 text-slate-100'
                  : 'text-slate-400 hover:text-slate-100 hover:bg-slate-800'
              }`
            }
          >
            <Icon size={16} />
            {t(`nav.${key}`)}
          </NavLink>
        ))}
      </nav>

      <div className="p-4 border-t border-slate-800 space-y-3">
        <LanguageSwitcher />
        {user && <p className="text-xs text-slate-500 truncate">{user.email}</p>}
        <button
          onClick={logout}
          className="flex items-center gap-2 text-xs text-slate-400 hover:text-red-400 transition-colors"
        >
          <LogOut size={14} />
          {t('nav.logout')}
        </button>
      </div>
    </div>
  )
}
