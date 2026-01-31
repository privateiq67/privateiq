"use client";
import React, { useState } from 'react';
import { Eye, TrendingUp } from 'lucide-react';

export default function Terminal() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [company, setCompany] = useState<any>(null);
  const [financials, setFinancials] = useState<any>(null);
  const [news, setNews] = useState([]);
  const [valuation, setValuation] = useState<any>(null); 
  const [loading, setLoading] = useState(false);

  // --- UPDATED FORMATTER: FULL NUMBERS ---
  // Uses "toLocaleString" to add commas (e.g. 100,000)
  const fmt = (val: any) => {
    if (!val && val !== 0) return <span className="text-slate-700">-</span>;
    // Format as GBP Currency, no decimal places for cleanliness
    return val.toLocaleString('en-GB', { 
      style: 'currency', 
      currency: 'GBP',
      maximumFractionDigits: 0 
    });
  };

  const pct = (num: any, den: any) => {
    if (!num || !den || den === 0) return <span className="text-slate-700">-</span>;
    return ((num / den) * 100).toFixed(1) + '%';
  };

  const mul = (num: any, den: any) => {
    if (!num || !den || den === 0) return <span className="text-slate-700">-</span>;
    return (num / den).toFixed(1) + 'x';
  };

  const search = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      // HARDCODED BACKEND URL
      const res = await fetch(`https://private-iq-backend.onrender.com/api/search?q=${query}`);
      const data = await res.json();
      setResults(data.items || []);
    } catch (err) { console.error(err); }
  };

  const loadCompany = async (c: any) => {
    setLoading(true);
    setCompany(c);
    setResults([]);
    setValuation(null);
    
    try {
      // HARDCODED BACKEND URL
      const finRes = await fetch(`https://private-iq-backend.onrender.com/api/company/${c.company_number}/financials`);
      const finData = await finRes.json();
      setFinancials(finData);

      if (c.title) {
        const params = new URLSearchParams({ name: c.title });
        // HARDCODED BACKEND URL
        const newsRes = await fetch(`https://private-iq-backend.onrender.com/api/news?${params.toString()}`);
        if (newsRes.ok) {
          const newsData = await newsRes.json();
          setNews(newsData.news || []);
          const valNews = newsData.news.find((n: any) => n.valuation_data);
          if (valNews) {
            setValuation({
              amount_m: valNews.valuation_data.amount_m,
              raw: valNews.valuation_data.raw,
              source: valNews.link,
              currency: valNews.valuation_data.currency
            });
          }
        }
      }
    } catch (err) { alert("Error loading data."); }
    setLoading(false);
  };

  return (
    <div className="min-h-screen bg-[#0a0f14] text-slate-200 font-sans p-6">
      <div className="max-w-7xl mx-auto">
        {/* Search */}
        <form onSubmit={search} className="flex gap-2 mb-6">
          <input 
            className="flex-1 bg-slate-900 border border-slate-700 p-3 rounded text-white focus:border-blue-500 outline-none"
            placeholder="Search UK Companies (e.g. Gymshark, Monzo)..."
            value={query} onChange={e => setQuery(e.target.value)}
          />
          <button className="bg-blue-600 px-6 rounded font-bold hover:bg-blue-500">Search</button>
        </form>

        {/* Results */}
        {results.length > 0 && (
          <div className="bg-slate-800 rounded mb-8 border border-slate-700">
            {results.map((r: any) => (
              <div key={r.company_number} onClick={() => loadCompany(r)} 
                   className="p-3 hover:bg-blue-600 cursor-pointer border-b border-slate-700 flex justify-between">
                <div className="font-bold">{r.title}</div>
                <div className="text-xs text-slate-400">{r.company_number}</div>
              </div>
            ))}
          </div>
        )}

        {loading && <div className="text-center text-blue-400 animate-pulse mt-12 font-bold">Scanning Documents & Calculating Units...</div>}

        {!loading && financials && company && (
          <div className="grid grid-cols-12 gap-6">
            
            {/* --- MAIN FINANCIALS (Left) --- */}
            <div className="col-span-8 space-y-6">
              
              {/* Valuation Card */}
              {valuation && financials.years[0] && (
                <div className="bg-slate-900 border border-blue-900/50 p-4 rounded flex items-center justify-between bg-gradient-to-r from-blue-900/20 to-transparent">
                  <div>
                    <div className="text-xs text-blue-400 uppercase font-bold tracking-wider mb-1">Implied Valuation (from News)</div>
                    <div className="text-2xl font-bold text-white">{valuation.raw}</div>
                    <a href={valuation.source} target="_blank" className="text-xs text-slate-500 hover:text-white underline">Source Article</a>
                  </div>
                  <div className="text-right">
                    <div className="text-xs text-slate-400 uppercase font-bold tracking-wider mb-1">Implied P/S Ratio</div>
                    {/* Backend sends full number now, so valuation must be scaled to Millions too for ratio */}
                    <div className="text-2xl font-mono text-green-400">
                        {mul(valuation.amount_m * 1000000, financials.years[0].income_statement.Revenue.value)}
                    </div>
                    <div className="text-xs text-slate-500">Based on latest revenue</div>
                  </div>
                </div>
              )}

              <div className="bg-slate-900 border border-slate-800 p-6 rounded">
                <div className="flex justify-between items-center mb-4">
                   <h2 className="text-2xl font-bold text-white">{company.title}</h2>
                   <div className="text-xs text-slate-500 uppercase tracking-widest">Figures in GBP (£)</div>
                </div>
                
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-slate-500 border-b border-slate-800">
                      <th className="text-left p-2 w-1/3">Item</th>
                      {financials.years.map((y: any, i: number) => (
                        <th key={i} className="text-right p-2">
                          {y.period}
                          {y.parsing_status.includes('pdf') && <span className="text-[9px] block text-yellow-500">PDF</span>}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/50">
                    
                    {/* INCOME STATEMENT */}
                    <tr className="bg-slate-950"><td colSpan={10} className="p-2 font-bold text-blue-400 text-xs uppercase">Income Statement</td></tr>
                    {["Revenue", "EBITDA (Est)", "EBIT", "Net Income"].map(row => (
                      <tr key={row}>
                          <td className="p-2 text-slate-300 pl-4">{row}</td>
                          {financials.years.map((y: any, i: number) => (
                              <td key={i} className="text-right p-2 font-mono">
                                  {fmt(y.income_statement[row]?.value)}
                                  {y.income_statement[row]?.source && (
                                      <a href={y.income_statement[row].source} target="_blank" className="ml-2 text-blue-500 hover:text-white"><Eye size={12} className="inline"/></a>
                                  )}
                              </td>
                          ))}
                      </tr>
                    ))}

                    {/* BALANCE SHEET */}
                    <tr className="bg-slate-950"><td colSpan={10} className="p-2 font-bold text-blue-400 text-xs uppercase">Balance Sheet</td></tr>
                    {["Current Assets", "Total Assets", "Current Liabilities", "Total Liabilities"].map(row => (
                      <tr key={row}>
                          <td className="p-2 text-slate-300 pl-4">{row}</td>
                          {financials.years.map((y: any, i: number) => (
                              <td key={i} className="text-right p-2 font-mono">{fmt(y.balance_sheet[row]?.value)}</td>
                          ))}
                      </tr>
                    ))}

                    {/* CASH FLOW */}
                    <tr className="bg-slate-950"><td colSpan={10} className="p-2 font-bold text-blue-400 text-xs uppercase">Cash Flow</td></tr>
                    {["Operating CF", "Investing CF", "Financing CF"].map(row => (
                      <tr key={row}>
                          <td className="p-2 text-slate-300 pl-4">{row}</td>
                          {financials.years.map((y: any, i: number) => (
                              <td key={i} className="text-right p-2 font-mono">{fmt(y.cash_flow[row]?.value)}</td>
                          ))}
                      </tr>
                    ))}

                    {/* RATIOS */}
                    <tr className="bg-blue-900/20"><td colSpan={10} className="p-2 font-bold text-green-400 text-xs uppercase border-t border-blue-800">Financial Ratios</td></tr>
                    <tr>
                      <td className="p-2 text-slate-300 pl-4">Net Margin %</td>
                      {financials.years.map((y: any, i: number) => (
                        <td key={i} className="text-right p-2 font-mono font-bold text-slate-200">
                          {pct(y.income_statement["Net Income"]?.value, y.income_statement["Revenue"]?.value)}
                        </td>
                      ))}
                    </tr>
                    <tr>
                      <td className="p-2 text-slate-300 pl-4">Current Ratio (x)</td>
                      {financials.years.map((y: any, i: number) => (
                        <td key={i} className="text-right p-2 font-mono text-slate-400">
                          {mul(y.balance_sheet["Current Assets"]?.value, y.balance_sheet["Current Liabilities"]?.value)}
                        </td>
                      ))}
                    </tr>

                  </tbody>
                </table>
              </div>
            </div>

            {/* --- NEWS SIDEBAR (Right) --- */}
            <div className="col-span-4">
              <div className="bg-slate-900 border border-slate-800 p-4 rounded h-fit sticky top-6">
                 <h3 className="font-bold text-slate-500 mb-4 text-xs tracking-wider flex items-center gap-2">
                   <TrendingUp size={14}/> MARKET INTEL
                 </h3>
                 {news.map((n: any, i) => (
                   <a key={i} href={n.link} target="_blank" className="block mb-3 p-3 bg-slate-950 hover:bg-slate-800 rounded border border-slate-800/50 transition group">
                     <div className="flex justify-between text-xs text-blue-400 mb-1">
                       <span>{new Date(n.published).toLocaleDateString()}</span>
                       {n.valuation_data && <span className="text-green-400 font-bold bg-green-900/30 px-1 rounded">VALUATION</span>}
                     </div>
                     <div className="text-sm font-semibold text-slate-300 leading-snug group-hover:text-white">{n.title}</div>
                   </a>
                 ))}
              </div>
            </div>

          </div>
        )}
      </div>
    </div>
  );
}
// Force rebuild for Hardcoded URL fix