"use client";
import React, { useEffect, useState } from "react";
import { TrendingUp, RefreshCw } from "lucide-react";
import { apiGet, NewsItem } from "../../lib/api";

export default function NewsPage() {
  const [news, setNews] = useState<NewsItem[]>([]);
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async (name?: string) => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (name) params.set("name", name);
      const data = await apiGet<{ news: NewsItem[] }>(`/api/news?${params.toString()}`);
      setNews(data.news || []);
    } catch (e: any) {
      setError(e.message || "Failed to load news");
      setNews([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  return (
    <div className="min-h-screen p-6">
      <div className="max-w-3xl mx-auto space-y-6">
        <div className="flex items-center justify-between gap-4">
          <h1 className="text-xl font-bold text-white flex items-center gap-2">
            <TrendingUp size={18} className="text-blue-400" /> Market Intel
          </h1>
          <button
            onClick={() => load(q || undefined)}
            className="text-xs flex items-center gap-1 text-slate-400 hover:text-white"
          >
            <RefreshCw size={12} /> Refresh
          </button>
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            load(q || undefined);
          }}
          className="flex gap-2"
        >
          <input
            className="flex-1 bg-slate-900 border border-slate-700 p-3 rounded text-white focus:border-blue-500 outline-none"
            placeholder="Filter by company (e.g. Monzo, Revolut)..."
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
          <button className="bg-blue-600 px-5 rounded font-bold hover:bg-blue-500">Search</button>
        </form>

        {loading && (
          <div className="text-center text-blue-400 animate-pulse py-12 font-medium">
            Loading feeds...
          </div>
        )}
        {error && (
          <div className="border border-red-900/50 bg-red-950/30 text-red-300 p-4 rounded text-sm">
            {error}
          </div>
        )}
        {!loading && !error && news.length === 0 && (
          <div className="text-slate-500 text-center py-12 text-sm">
            No articles found. Try another query or check network access to RSS feeds.
          </div>
        )}

        <div className="space-y-3">
          {news.map((n, i) => (
            <a
              key={i}
              href={n.link}
              target="_blank"
              rel="noreferrer"
              className="block p-4 bg-slate-900 border border-slate-800 hover:border-slate-600 rounded transition"
            >
              <div className="flex justify-between text-xs text-blue-400 mb-1 gap-2">
                <span>
                  {n.source}
                  {n.published ? ` · ${new Date(n.published).toLocaleDateString("en-GB")}` : ""}
                </span>
                {n.valuation_data && (
                  <span className="text-green-400 font-bold bg-green-900/30 px-1.5 rounded">
                    {n.valuation_data.raw}
                  </span>
                )}
              </div>
              <div className="text-sm font-semibold text-slate-200 leading-snug">{n.title}</div>
            </a>
          ))}
        </div>
      </div>
    </div>
  );
}
