import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Activity, AlertTriangle, CircleDot, Play, Plus, Square, Trash2 } from 'lucide-react'
import { api } from '../api'
import type { Bot } from '../types'
import Badge from '../components/Badge'

function pnlClass(v: number) {
  return v > 0 ? 'text-emerald-400' : v < 0 ? 'text-red-400' : 'text-slate-300'
}

function money(v: number) {
  return `${v >= 0 ? '+' : ''}${v.toFixed(2)}`
}

export default function Bots() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const { data: bots = [] } = useQuery({ queryKey: ['bots'], queryFn: api.listBots })

  const refresh = () => qc.invalidateQueries({ queryKey: ['bots'] })
  const start = useMutation({ mutationFn: api.startBot, onSuccess: refresh })
  const stop = useMutation({ mutationFn: api.stopBot, onSuccess: refresh })
  const del = useMutation({ mutationFn: api.deleteBot, onSuccess: refresh })

  return (
    <div className="max-w-4xl space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-slate-100">{t('bots.title')}</h1>
        <Link
          to="/bots/new"
          className="flex items-center gap-1.5 bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-medium px-3 py-1.5 rounded-md transition-colors"
        >
          <Plus size={15} />
          {t('bots.create')}
        </Link>
      </div>

      {bots.length === 0 && (
        <div className="bg-slate-900 border border-slate-800 rounded-lg p-8 text-center text-slate-500 text-sm">
          {t('bots.noBots')}
        </div>
      )}

      <div className="space-y-3">
        {bots.map((b) => (
          <BotCard
            key={b.id}
            bot={b}
            onStart={() => start.mutate(b.id)}
            onStop={() => stop.mutate(b.id)}
            onDelete={() => confirm(t('bots.deleteConfirm')) && del.mutate(b.id)}
            busy={start.isPending || stop.isPending}
          />
        ))}
      </div>
    </div>
  )
}

function BotCard({
  bot,
  onStart,
  onStop,
  onDelete,
  busy,
}: {
  bot: Bot
  onStart: () => void
  onStop: () => void
  onDelete: () => void
  busy: boolean
}) {
  const { t } = useTranslation()
  const running = bot.runtime.running
  const lastTick = bot.runtime.last_tick_at
    ? new Date(bot.runtime.last_tick_at).toLocaleTimeString()
    : t('bots.never')

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            {running ? (
              <Activity size={15} className="text-emerald-400" />
            ) : (
              <CircleDot size={15} className="text-slate-500" />
            )}
            <Link to={`/bots/${bot.id}`} className="font-medium text-slate-100 hover:text-emerald-400">
              {bot.name}
            </Link>
            <span className="text-xs text-slate-500">{bot.symbol} {bot.leverage}x</span>
            <Badge
              label={bot.direction === 'LONG' ? t('side.long') : t('side.short')}
              variant={bot.direction === 'LONG' ? 'green' : 'red'}
            />
          </div>
          <div className="text-xs text-slate-500 mt-1">
            {t('bots.account')}: {bot.account_name} · {t('bots.openOrders')}: {bot.runtime.open_orders} · {t('bots.lastTick')}: {lastTick}
          </div>
          {bot.runtime.last_error && (
            <div className="flex items-center gap-1.5 text-xs text-red-400 mt-1">
              <AlertTriangle size={12} />
              {bot.runtime.last_error}
            </div>
          )}
        </div>

        <div className="text-right shrink-0">
          <div className={`text-lg font-semibold ${pnlClass(bot.pnl.total)}`}>${money(bot.pnl.total)}</div>
          <div className="text-xs text-slate-500">
            {t('bots.realized')} {money(bot.pnl.realized)} · {t('bots.unrealized')} {money(bot.pnl.unrealized)}
          </div>
        </div>
      </div>

      <div className="flex items-center gap-2 mt-3">
        {running ? (
          <button
            onClick={onStop}
            disabled={busy}
            title={t('bots.stopHint')}
            className="flex items-center gap-1.5 bg-red-600 hover:bg-red-500 disabled:opacity-50 text-white text-sm px-3 py-1.5 rounded-md transition-colors"
          >
            <Square size={13} />
            {t('bots.stop')}
          </button>
        ) : (
          <button
            onClick={onStart}
            disabled={busy}
            className="flex items-center gap-1.5 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white text-sm px-3 py-1.5 rounded-md transition-colors"
          >
            <Play size={13} />
            {t('bots.start')}
          </button>
        )}
        <Link
          to={`/bots/${bot.id}`}
          className="text-sm text-slate-400 hover:text-slate-100 px-3 py-1.5 rounded-md hover:bg-slate-800 transition-colors"
        >
          {t('bots.details')}
        </Link>
        <button
          onClick={onDelete}
          className="ml-auto text-slate-500 hover:text-red-400 transition-colors"
          title={t('bots.delete')}
        >
          <Trash2 size={15} />
        </button>
      </div>
    </div>
  )
}
