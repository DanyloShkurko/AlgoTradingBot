interface StatCardProps {
  label: string
  value: string
  sub?: string
  positive?: boolean
  negative?: boolean
}

export default function StatCard({ label, value, sub, positive, negative }: StatCardProps) {
  const valueClass = positive
    ? 'text-emerald-400'
    : negative
    ? 'text-red-400'
    : 'text-slate-100'

  return (
    <div className="bg-slate-900 rounded-lg border border-slate-800 p-4">
      <p className="text-xs text-slate-500 uppercase tracking-wide mb-1">{label}</p>
      <p className={`text-2xl font-semibold ${valueClass}`}>{value}</p>
      {sub && <p className="text-xs text-slate-500 mt-1">{sub}</p>}
    </div>
  )
}
