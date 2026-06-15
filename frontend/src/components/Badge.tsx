type Variant = 'green' | 'red' | 'yellow' | 'slate'

const variants: Record<Variant, string> = {
  green: 'bg-emerald-900/50 text-emerald-400',
  red: 'bg-red-900/50 text-red-400',
  yellow: 'bg-yellow-900/50 text-yellow-400',
  slate: 'bg-slate-800 text-slate-400',
}

export default function Badge({ label, variant = 'slate' }: { label: string; variant?: Variant }) {
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${variants[variant]}`}>
      {label}
    </span>
  )
}
