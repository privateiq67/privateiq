export default function StatusBadge({ status }: { status?: string }) {
  const s = (status || "partial").toLowerCase();
  const styles: Record<string, string> = {
    ixbrl: "bg-emerald-900/40 text-emerald-300 border-emerald-700/50",
    pdf: "bg-amber-900/40 text-amber-300 border-amber-700/50",
    fixture: "bg-violet-900/40 text-violet-300 border-violet-700/50",
    partial: "bg-slate-800 text-slate-400 border-slate-700",
    failed: "bg-red-900/40 text-red-300 border-red-700/50",
  };
  const cls = styles[s] || styles.partial;
  return (
    <span className={`text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded border ${cls}`}>
      {s}
    </span>
  );
}
