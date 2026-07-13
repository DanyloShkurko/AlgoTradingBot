import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery } from '@tanstack/react-query'
import { ArrowLeft } from 'lucide-react'
import { api } from '../api'
import type { BotCreate } from '../types'
import BotStrategyFields, { Field, inputClass, type BotFormValues } from '../components/BotStrategyFields'

const defaults: BotFormValues = {
  name: '',
  symbol: 'BTCUSDT',
  direction: 'LONG',
  entry_price: 0,
  leverage: 10,
  target_position_pct: 15,
  dca_step_pct: 2,
  dca_add_pct: 20,
  take_profit_pct: 20,
  take_profit_close_pct: 33,
  tp_width_pct: 100,
  max_dca_orders: 8,
}

export default function CreateBot() {
  const { t } = useTranslation()
  const nav = useNavigate()
  const { data: accounts = [] } = useQuery({ queryKey: ['accounts'], queryFn: api.listAccounts })
  const [form, setForm] = useState<BotFormValues>(defaults)
  const [accountId, setAccountId] = useState<number | null>(null)

  const effectiveAccount = accountId ?? accounts[0]?.id ?? null

  const create = useMutation({
    mutationFn: () => api.createBot({ ...form, account_id: effectiveAccount! } as BotCreate),
    onSuccess: () => nav('/bots'),
  })

  const set = <K extends keyof BotFormValues>(key: K, value: BotFormValues[K]) =>
    setForm((prev) => ({ ...prev, [key]: value }))

  return (
    <div className="max-w-xl space-y-6">
      <div className="flex items-center gap-2">
        <Link to="/bots" className="text-slate-500 hover:text-slate-100">
          <ArrowLeft size={18} />
        </Link>
        <h1 className="text-lg font-semibold text-slate-100">{t('createBot.title')}</h1>
      </div>

      {accounts.length === 0 ? (
        <div className="bg-slate-900 border border-slate-800 rounded-lg p-6 text-center text-sm text-slate-400">
          {t('createBot.noAccounts')}{' '}
          <Link to="/accounts" className="text-emerald-400 hover:text-emerald-300">
            {t('nav.accounts')}
          </Link>
        </div>
      ) : (
        <>
          <BotStrategyFields
            form={form}
            set={set}
            accountSlot={
              <Field label={t('createBot.account')}>
                <select
                  className={inputClass}
                  value={effectiveAccount ?? ''}
                  onChange={(e) => setAccountId(Number(e.target.value))}
                >
                  {accounts.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name} {a.testnet ? '(testnet)' : ''}
                    </option>
                  ))}
                </select>
              </Field>
            }
          />

          {create.isError && <div className="text-sm text-red-400">{(create.error as Error).message}</div>}

          <button
            onClick={() => create.mutate()}
            disabled={create.isPending || !effectiveAccount}
            className="w-full bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 text-white font-medium py-2 rounded-md transition-colors text-sm"
          >
            {create.isPending ? t('common.creating') : t('createBot.submit')}
          </button>
        </>
      )}
    </div>
  )
}
