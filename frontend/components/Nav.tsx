"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Search, Newspaper, Activity } from "lucide-react";

export default function Nav() {
  const path = usePathname();
  const link = (href: string, label: string, Icon: any) => {
    const active = path === href;
    return (
      <Link
        href={href}
        className={`flex items-center gap-2 px-3 py-2 rounded text-sm font-medium transition ${
          active
            ? "bg-blue-600/30 text-blue-300 border border-blue-700/50"
            : "text-slate-400 hover:text-white hover:bg-slate-800/80"
        }`}
      >
        <Icon size={14} />
        {label}
      </Link>
    );
  };

  return (
    <header className="border-b border-slate-800 bg-[#070b10]/95 backdrop-blur sticky top-0 z-40">
      <div className="max-w-7xl mx-auto px-6 py-3 flex items-center justify-between gap-4">
        <Link href="/" className="flex items-center gap-2 font-bold tracking-tight text-white">
          <Activity className="text-blue-400" size={18} />
          PrivateIQ
          <span className="text-[10px] uppercase tracking-widest text-slate-500 font-normal ml-1">
            UK Private Markets
          </span>
        </Link>
        <nav className="flex items-center gap-1">
          {link("/", "Search", Search)}
          {link("/news", "News", Newspaper)}
        </nav>
      </div>
    </header>
  );
}
