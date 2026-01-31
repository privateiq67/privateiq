"use client";
import React, { useState } from 'react';
import { Search, Eye, AlertCircle, CheckCircle } from 'lucide-react';

export default function Terminal() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [company, setCompany] = useState<any>(null);
  const [financials, setFinancials] = useState<any>(null);
  const [news, setNews] = useState([]);
  const [loading, setLoading] = useState(false);

  // 1. Search Function
  const search = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await fetch(`http://127.0.0.1:8000/api/search?q=${query}`);
      const data = await res.json();
      setResults(data.items || []);
    } catch (err) {
      console.error("Search failed", err);
    }
  };

  // 2. Load Company Details (FIXED for special characters)
  const loadCompany = async (c: any) => {
    setLoading(true);
    setCompany(c);
    setResults([]);
    
    try {
      // A. Fetch Financials (Uses ID, safe)
      const finRes = await fetch(`http://127.0.0.1:8000/api/company/${c.company_number}/financials`);
      const finData = await finRes.json();
      setFinancials(finData);

// ... inside loadCompany function ...

      // 2. Fetch News (FIXED: Using Query Parameter)
      if (c.title) {
        // We use URLSearchParams to ensure the name is encoded perfectly
        const params = new URLSearchParams({ name: c.title });
        
        // OLD WAY (Avoid this): 
        // const newsRes = await fetch(`http://127.0.0.1:8000/api/company/${safeName}/news`);
        
        // NEW WAY (Robust):
        const newsRes = await fetch(`http://127.0.0.1:8000/api/news?${params.toString()}`);
        
        if (newsRes.ok) {
          const newsData = await newsRes.json();
          setNews(newsData.news || []);
        } else {
          setNews([]);
        }
      }
    } catch (err) {
      console.error("Connection Error:", err);
      alert("Error connecting to Backend. Is Python running?");
    }
    
    setLoading(false);
  };

  return (
    <div className="min-h-screen bg-[#0a0f14] text-slate-200 font-sans p-6">
      <div className="max-w-6xl mx-auto">
        {/* SEARCH */}
        <form onSubmit={search} className="flex gap-2 mb-4">
          <input 
            className="flex-1 bg-slate-900 border border-slate-700 p-3 rounded text-white"
            placeholder="Search UK Companies..."
            value={query} onChange={e => setQuery(e.target.value)}
          />
          <button className="bg-blue-600 px-6 rounded font-bold">Search</button>
        </form>

        {/* RESULTS LIST */}
        {results.length > 0 && (
          <div className="bg-slate-800 rounded mb-8">
            {results.map((r: any) => (
              <div key={r.company_number} onClick={() => loadCompany(r)} 
                   className="p-3 hover:bg-blue-600 cursor-pointer border-b border-slate-700">
                <div className="font-bold">{r.title}</div>
                <div className="text-xs text-slate-400">{r.company_number}</div>
              </div>
            ))}
          </div>
        )}

        {/* LOADING INDICATOR */}
        {loading && <div className="text-blue-400 animate-pulse mt-10 text-center">Fetching Government Data...</div>}

        {/* MAIN DASHBOARD */}
        {!loading && financials && company && (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            
            {/* LEFT: FINANCIALS TABLE */}
            <div className="md:col-span-2 bg-slate-900 border border-slate-800 p-6 rounded">
              <h2 className="text-2xl font-bold mb-4 text-white">{company.title}</h2>
              
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-slate-500 border-b border-slate-800">
                    <th className="text-left p-2">Item</th>
                    {financials.years.map((y: any, i: number) => (
                      <th key={i} className="text-right p-2 w-24">
                        {y.period}
                        {/* Status Icon: Green Check or Yellow Alert */}
                        {y.parsing_status === 'success' ? 
                          <CheckCircle size={12} className="inline ml-1 text-green-500"/> : 
                          <AlertCircle size={12} className="inline ml-1 text-yellow-500"/>
                        }
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {/* REVENUE */}
                  <tr>
                    <td className="p-2 text-slate-400">Revenue</td>
                    {financials.years.map((y: any, i: number) => (
                      <td key={i} className="text-right p-2 font-mono">
                        {y.income_statement.Revenue.value ? 
                          (y.income_statement.Revenue.value / 1000000).toFixed(1) + 'M' : 
                          <span className="text-slate-600">-</span>
                        }
                        <a href={y.income_statement.Revenue.source} target="_blank" className="ml-2 text-blue-400 hover:text-white">
                          <Eye size={12} className="inline"/>
                        </a>
                      </td>
                    ))}
                  </tr>
                   {/* PROFIT */}
                   <tr>
                    <td className="p-2 text-slate-400">Op. Profit</td>
                    {financials.years.map((y: any, i: number) => (
                      <td key={i} className="text-right p-2 font-mono">
                        {y.income_statement["Operating Profit"].value ? 
                          (y.income_statement["Operating Profit"].value / 1000000).toFixed(1) + 'M' : 
                          <span className="text-slate-600">-</span>
                        }
                      </td>
                    ))}
                  </tr>
                   {/* NET ASSETS */}
                   <tr>
                    <td className="p-2 text-slate-400">Net Assets</td>
                    {financials.years.map((y: any, i: number) => (
                      <td key={i} className="text-right p-2 font-mono">
                        {y.balance_sheet["Net Assets"].value ? 
                          (y.balance_sheet["Net Assets"].value / 1000000).toFixed(1) + 'M' : 
                          <span className="text-slate-600">-</span>
                        }
                      </td>
                    ))}
                  </tr>
                   {/* CASH */}
                   <tr>
                    <td className="p-2 text-slate-400">Cash</td>
                    {financials.years.map((y: any, i: number) => (
                      <td key={i} className="text-right p-2 font-mono">
                        {y.balance_sheet["Cash"].value ? 
                          (y.balance_sheet["Cash"].value / 1000000).toFixed(1) + 'M' : 
                          <span className="text-slate-600">-</span>
                        }
                      </td>
                    ))}
                  </tr>
                </tbody>
              </table>
            </div>

            {/* RIGHT: NEWS FEED */}
            <div className="bg-slate-900 border border-slate-800 p-4 rounded h-fit">
               <h3 className="font-bold text-slate-500 mb-4">MARKET INTEL</h3>
               {news.map((n: any, i) => (
                 <a key={i} href={n.link} target="_blank" className="block mb-3 p-3 bg-slate-950 hover:bg-slate-800 rounded border border-slate-800">
                   <div className="text-xs text-blue-400 mb-1">{new Date(n.published).toLocaleDateString()}</div>
                   <div className="text-sm font-semibold text-slate-300">{n.title}</div>
                 </a>
               ))}
               {news.length === 0 && <div className="text-slate-600 text-sm">No recent news found.</div>}
            </div>

          </div>
        )}
      </div>
    </div>
  );
}