import { useTranslation } from 'react-i18next'

const langs = [
  { code: 'ru', label: 'RU' },
  { code: 'en', label: 'EN' },
]

export default function LanguageSwitcher() {
  const { i18n } = useTranslation()
  const current = i18n.language?.startsWith('ru') ? 'ru' : 'en'

  return (
    <div className="flex gap-1">
      {langs.map(({ code, label }) => (
        <button
          key={code}
          onClick={() => {
            i18n.changeLanguage(code)
            localStorage.setItem('lang', code)
          }}
          className={`px-2 py-1 rounded text-xs font-medium transition-colors ${
            current === code
              ? 'bg-slate-700 text-slate-100'
              : 'text-slate-500 hover:text-slate-300'
          }`}
        >
          {label}
        </button>
      ))}
    </div>
  )
}
