import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, AlertTriangle } from 'lucide-react'
import { api } from '../api'
import type { Bot } from '../types'
import BotStrategyFields, { type BotFormValues } from '../components/BotStrategyFields'

function toForm(bot: Bot): BotFormValues {
  return {
    name: bot.name,
    symbol: bot.symbol,
    direction: bot.direction,
    entry_price: bot.entry_price,
    leverage: bot.leverage,
    target_position_pct: bot.target_position_pct,
    dca_step_pct: bot.dca_step_pct,
    dca_add_pct: bot.dca_add_pct,
    take_profit_pct: bot.take_profit_pct,
    take_profit_close_pct: bot.take_profit_close_pct,
    tp_width_pct: bot.tp_width_pct,
    max_dca_orders: bot.max_dca_orders,
  }
}

export default function EditBot() {
  const { t } = useTranslation()
  const nav = useNavigate()
  const qc = useQueryClient()
  const id = Number(useParams().id)
  const { data: bot } = useQuery({ queryKey: ['bot', id], queryFn: () => api.getBot(id) })
  const [form, setForm] = useState<BotFormValues | null>(null)

  useEffect(() => {
    if (bot) setForm((prev) => prev ?? toForm(bot))
  }, [bot])

  const running = bot?.enabled ?? false

  const save = useMutation({
    mutationFn: () => api.updateBot(id, form!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['bot', id] })
      qc.invalidateQueries({ queryKey: ['bots'] })
      nav(`/bots/${id}`)
    },
  })

  const set = <K extends keyof BotFormValues>(key: K, value: BotFormValues[K]) =>
    setForm((prev) => (prev ? { ...prev, [key]: value } : prev))

  if (!bot || !form) return <div className="text-sm text-slate-400">{t('common.loading')}</div>

  return (
    <div className="max-w-xl space-y-6">
      <div className="flex items-center gap-2">
        <Link to={`/bots/${id}`} className="text-slate-500 hover:text-slate-100">
          <ArrowLeft size={18} />
        </Link>
        <h1 className="text-lg font-semibold text-slate-100">{t('editBot.title')}</h1>
      </div>

      {running && (
        <div className="flex items-start gap-2 text-sm text-amber-400 bg-amber-900/20 rounded-md px-3 py-2">
          <AlertTriangle size={15} className="mt-0.5 shrink-0" />
          <span>{t('editBot.runningWarn')}</span>
        </div>
      )}

      <BotStrategyFields form={form} set={set} lockStructural={running} />

      {save.isError && <div className="text-sm text-red-400">{(save.error as Error).message}</div>}

      <button
        onClick={() => save.mutate()}
        disabled={save.isPending}
        className="w-full bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 text-white font-medium py-2 rounded-md transition-colors text-sm"
      >
        {save.isPending ? t('common.saving') : t('editBot.submit')}
      </button>
    </div>
  )
}
