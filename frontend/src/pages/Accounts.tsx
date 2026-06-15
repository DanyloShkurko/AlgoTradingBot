import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle2, Trash2, XCircle } from 'lucide-react'
import { api } from '../api'
import type { ConnectionTest } from '../types'

const inputClass =
  'w-full bg-slate-800 border border-slate-700 rounded-md px-3 py-2 text-sm text-slate-100 focus:outline-none focus:ring-1 focus:ring-emerald-500'

export default function Accounts() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const { data: accounts = [] } = useQuery({ queryKey: ['accounts'], queryFn: api.listAccounts })

  const [name, setName] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [apiSecret, setApiSecret] = useState('')
  const [testnet, setTestnet] = useState(true)
  const [tests, setTests] = useState<Record<number, ConnectionTest>>({})

  const create = useMutation({
    mutationFn: () => api.createAccount({ name, api_key: apiKey, api_secret: apiSecret, testnet }),
    onSuccess: () => {
      setName(''); setApiKey(''); setApiSecret('')
      qc.invalidateQueries({ queryKey: ['accounts'] })
    },
  })

  const del = useMutation({
    mutationFn: (id: number) => api.deleteAccount(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['accounts'] }),
  })

  const test = useMutation({
    mutationFn: (id: number) => api.testAccount(id),
    onSuccess: (res, id) => setTests((prev) => ({ ...prev, [id]: res })),
  })

  const submit = () => {
    // Real-money accounts require explicit confirmation.
    if (!testnet && !confirm(t('accounts.mainnetConfirm'))) return
    create.mutate()
  }

  return (
    <div className="max-w-2xl space-y-6">
      <div>
        <h1 className="text-lg font-semibold text-slate-100">{t('accounts.title')}</h1>
        <p className="text-sm text-slate-500 mt-1">{t('accounts.subtitle')}</p>
      </div>

      {/* existing accounts */}
      <div className="space-y-3">
        {accounts.length === 0 && (
          <div className="bg-slate-900 border border-slate-800 rounded-lg p-6 text-center text-slate-500 text-sm">
            {t('accounts.noAccounts')}
          </div>
        )}
        {accounts.map((a) => (
          <div key={a.id} className="bg-slate-900 border border-slate-800 rounded-lg p-4">
            <div className="flex items-center justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-medium text-slate-100">{a.name}</span>
                  <span
                    className={`text-xs px-2 py-0.5 rounded font-medium ${
                      a.testnet ? 'bg-yellow-900/40 text-yellow-400' : 'bg-red-900/50 text-red-300'
                    }`}
                  >
                    {a.testnet ? t('accounts.testnet') : 'MAINNET'}
                  </span>
                </div>
                <code className="text-xs text-slate-500">{a.api_key_masked}</code>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => test.mutate(a.id)}
                  disabled={test.isPending}
                  className="text-xs bg-slate-700 hover:bg-slate-600 text-slate-100 px-3 py-1.5 rounded-md transition-colors"
                >
                  {test.isPending && test.variables === a.id ? t('accounts.testing') : t('accounts.test')}
                </button>
                <button
                  onClick={() => confirm(t('accounts.deleteConfirm')) && del.mutate(a.id)}
                  className="text-slate-500 hover:text-red-400 transition-colors"
                  title={t('common.delete')}
                >
                  <Trash2 size={16} />
                </button>
              </div>
            </div>
            {tests[a.id] && (
              <div
                className={`mt-3 flex items-start gap-2 text-sm rounded-md p-2.5 ${
                  tests[a.id].ok ? 'bg-emerald-900/30 text-emerald-300' : 'bg-red-900/30 text-red-300'
                }`}
              >
                {tests[a.id].ok ? (
                  <CheckCircle2 size={15} className="mt-0.5 shrink-0" />
                ) : (
                  <XCircle size={15} className="mt-0.5 shrink-0" />
                )}
                <span>
                  {tests[a.id].ok
                    ? t('accounts.connectionOk', { balance: tests[a.id].total_wallet_balance?.toFixed(2) })
                    : t('accounts.connectionFailed', { error: tests[a.id].error })}
                </span>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* add account */}
      <div className="bg-slate-900 border border-slate-800 rounded-lg p-5 space-y-4">
        <h2 className="text-xs font-medium text-slate-500 uppercase tracking-wide">{t('accounts.add')}</h2>
        <div>
          <label className="block text-sm text-slate-400 mb-1">{t('accounts.name')}</label>
          <input className={inputClass} value={name} placeholder={t('accounts.namePlaceholder')} onChange={(e) => setName(e.target.value)} />
        </div>
        <div>
          <label className="block text-sm text-slate-400 mb-1">{t('accounts.apiKey')}</label>
          <input className={inputClass} value={apiKey} autoComplete="off" spellCheck={false} onChange={(e) => setApiKey(e.target.value)} />
        </div>
        <div>
          <label className="block text-sm text-slate-400 mb-1">{t('accounts.apiSecret')}</label>
          <input type="password" className={inputClass} value={apiSecret} autoComplete="off" spellCheck={false} placeholder={t('accounts.secretPlaceholder')} onChange={(e) => setApiSecret(e.target.value)} />
        </div>
        <label className="flex items-center justify-between cursor-pointer select-none">
          <span className="text-sm text-slate-300">{t('accounts.testnet')}</span>
          <button
            type="button"
            onClick={() => setTestnet((v) => !v)}
            className={`relative w-10 h-5 rounded-full transition-colors ${testnet ? 'bg-emerald-500' : 'bg-red-600'}`}
          >
            <span className={`absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform ${testnet ? 'translate-x-5' : ''}`} />
          </button>
        </label>
        {!testnet && (
          <div className="flex items-start gap-2 text-xs text-red-300 bg-red-900/25 rounded-md px-3 py-2">
            <AlertTriangle size={14} className="mt-0.5 shrink-0" />
            <span>{t('accounts.mainnetWarn')}</span>
          </div>
        )}
        {create.isError && <div className="text-sm text-red-400">{(create.error as Error).message}</div>}
        <button
          onClick={submit}
          disabled={create.isPending || !name || !apiKey || !apiSecret}
          className={`w-full disabled:opacity-40 text-white font-medium py-2 rounded-md transition-colors text-sm ${
            testnet ? 'bg-emerald-600 hover:bg-emerald-500' : 'bg-red-600 hover:bg-red-500'
          }`}
        >
          {create.isPending ? t('common.creating') : testnet ? t('accounts.save') : t('accounts.saveMainnet')}
        </button>
        <p className="text-xs text-slate-600">{t('accounts.getKeys')}</p>
      </div>
    </div>
  )
}
