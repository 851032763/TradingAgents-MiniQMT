import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeft, Download, Eye, Loader2, Play, RefreshCw, Search, Trash2 } from 'lucide-react'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '@/services/api'
import type { KronosPredictionRun } from '@/types'

const PAGE_SIZE = 20

function number(value: number | null | undefined, digits = 2) {
    return value == null || !Number.isFinite(value) ? '--' : value.toLocaleString('zh-CN', { minimumFractionDigits: digits, maximumFractionDigits: digits })
}

function time(value?: string | null) {
    if (!value) return '--'
    const date = new Date(value)
    return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false })
}

function date(value: string) { return value.slice(0, 10).replace(/-/g, '/') }

function saveFile(name: string, content: string, type: string) {
    const url = URL.createObjectURL(new Blob([content], { type }))
    const anchor = document.createElement('a')
    anchor.href = url; anchor.download = name; anchor.click()
    URL.revokeObjectURL(url)
}

function chartData(run: KronosPredictionRun) {
    const history = (run.input_klines || []).slice(-80).map(item => ({ date: item.date, actual: Number(item.close) }))
    if (!history.length) return history
    const last = history[history.length - 1]
    const forecast = (run.predictions || []).flatMap((item, index) => {
        const forecastDate = run.forecast_dates?.[index]
        return forecastDate ? [{ date: forecastDate, forecast: Number(item.close) }] : []
    })
    return [...history.slice(0, -1), { ...last, forecast: last.actual }, ...forecast]
}

export default function KronosHistory() {
    const [runs, setRuns] = useState<KronosPredictionRun[]>([])
    const [total, setTotal] = useState(0)
    const [skip, setSkip] = useState(0)
    const [symbol, setSymbol] = useState('')
    const [status, setStatus] = useState('')
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)
    const [selected, setSelected] = useState<KronosPredictionRun | null>(null)
    const [selectedIds, setSelectedIds] = useState<string[]>([])
    const [busyId, setBusyId] = useState<string | null>(null)
    const [rerunJob, setRerunJob] = useState<{ id: string; symbol: string; startedAt: number } | null>(null)
    const [elapsedSeconds, setElapsedSeconds] = useState(0)

    useEffect(() => {
        if (!rerunJob) return
        const refreshElapsed = () => setElapsedSeconds(Math.max(0, Math.floor((Date.now() - rerunJob.startedAt) / 1000)))
        refreshElapsed()
        const timer = window.setInterval(refreshElapsed, 1000)
        return () => window.clearInterval(timer)
    }, [rerunJob])

    const load = useCallback(async () => {
        setLoading(true); setError(null)
        try {
            const response = await api.getKronosPredictionRuns({ symbol: symbol.trim().toUpperCase() || undefined, status: status || undefined, skip, limit: PAGE_SIZE })
            setRuns(response.runs); setTotal(response.total); setSelectedIds(ids => ids.filter(id => response.runs.some(run => run.id === id)))
        } catch (err) { setError(err instanceof Error ? err.message : '加载预测记录失败') } finally { setLoading(false) }
    }, [skip, status, symbol])

    useEffect(() => { void load() }, [load])

    const open = async (id: string) => {
        setBusyId(id); setError(null)
        try { setSelected(await api.getKronosPredictionRun(id)) } catch (err) { setError(err instanceof Error ? err.message : '加载预测快照失败') } finally { setBusyId(null) }
    }
    const remove = async (id: string) => {
        if (!window.confirm('确定删除这条预测记录吗？此操作无法撤销。')) return
        setBusyId(id); try { await api.deleteKronosPredictionRun(id); if (selected?.id === id) setSelected(null); await load() } catch (err) { setError(err instanceof Error ? err.message : '删除失败') } finally { setBusyId(null) }
    }
    const removeSelected = async () => {
        if (!selectedIds.length || !window.confirm(`确定删除选中的 ${selectedIds.length} 条预测记录吗？`)) return
        setBusyId('batch'); try { await api.deleteKronosPredictionRuns(selectedIds); setSelectedIds([]); setSelected(null); await load() } catch (err) { setError(err instanceof Error ? err.message : '批量删除失败') } finally { setBusyId(null) }
    }
    const rerun = async (run: KronosPredictionRun) => {
        if (rerunJob) return
        const job = { id: run.id, symbol: run.symbol, startedAt: Date.now() }
        setBusyId(run.id); setRerunJob(job); setError(null)
        // Let React paint the running notice before the synchronous API call starts.
        await new Promise<void>(resolve => window.requestAnimationFrame(() => resolve()))
        try {
            const next = await api.createKronosPredictionRun({ symbol: run.symbol, frequency: run.frequency, lookback: run.lookback_requested, pred_len: run.pred_len, temperature: run.temperature, top_p: run.top_p, sample_count: run.sample_count, model_key: run.model_key })
            if (next.status !== 'completed') throw new Error(next.error_message || '重新预测未完成')
            setSelected(next); setSkip(0); await load()
        } catch (err) {
            setError(err instanceof Error ? err.message : '重新预测失败')
        } finally {
            setBusyId(null); setRerunJob(null)
        }
    }
    const exportJson = (run: KronosPredictionRun) => saveFile(`kronos-${run.symbol}-${run.id}.json`, JSON.stringify(run, null, 2), 'application/json')
    const exportCsv = (run: KronosPredictionRun) => {
        const rows = [['date', 'kind', 'open', 'high', 'low', 'close', 'volume', 'amount']]
        for (const item of run.input_klines || []) rows.push([item.date, 'history', item.open, item.high, item.low, item.close, item.volume, item.amount].map(String))
        for (const [index, item] of (run.predictions || []).entries()) rows.push([run.forecast_dates?.[index] || '', 'forecast', item.open, item.high, item.low, item.close, item.volume, item.amount].map(String))
        saveFile(`kronos-${run.symbol}-${run.id}.csv`, `\uFEFF${rows.map(row => row.join(',')).join('\n')}`, 'text/csv;charset=utf-8')
    }
    const detailChart = useMemo(() => selected ? chartData(selected) : [], [selected])

    if (selected) return <KronosDetail run={selected} data={detailChart} busy={rerunJob?.id === selected.id} rerunJob={rerunJob} elapsedSeconds={elapsedSeconds} onBack={() => setSelected(null)} onRerun={() => void rerun(selected)} onExportJson={() => exportJson(selected)} onExportCsv={() => exportCsv(selected)} onDelete={() => void remove(selected.id)} />

    return <div className="space-y-6">
        <header className="flex flex-wrap items-start justify-between gap-4"><div><Link to="/kronos" className="mb-3 inline-flex items-center gap-1 text-sm text-slate-500 hover:text-blue-600"><ArrowLeft className="h-4 w-4" />返回 Kronos 预测</Link><p className="text-xs font-semibold uppercase tracking-[0.18em] text-cyan-600 dark:text-cyan-300">Forecast Archive</p><h1 className="mt-1 text-2xl font-bold text-slate-900 dark:text-slate-100">预测记录</h1><p className="mt-2 text-sm text-slate-500 dark:text-slate-400">保存每次推理的输入行情、参数、交易日和预测结果，可随时复盘。</p></div><button onClick={() => void load()} disabled={Boolean(rerunJob)} className="btn-secondary flex items-center gap-2"><RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />刷新</button></header>
        {rerunJob && <RerunProgress symbol={rerunJob.symbol} elapsedSeconds={elapsedSeconds} />}
        <section className="card space-y-4 p-4"><div className="flex flex-wrap gap-3"><label className="relative min-w-[210px] flex-1"><Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" /><input value={symbol} onChange={event => { setSymbol(event.target.value); setSkip(0) }} placeholder="筛选股票代码" className="input w-full pl-9 font-mono" /></label><select value={status} onChange={event => { setStatus(event.target.value); setSkip(0) }} className="input w-36"><option value="">全部状态</option><option value="completed">已完成</option><option value="failed">失败</option><option value="running">运行中</option></select>{selectedIds.length > 0 && <button onClick={() => void removeSelected()} disabled={busyId === 'batch'} className="btn-secondary flex items-center gap-2 text-rose-600 hover:text-rose-700"><Trash2 className="h-4 w-4" />删除 {selectedIds.length} 条</button>}</div>{error && <p className="text-sm text-rose-600 dark:text-rose-300">{error}</p>}</section>
        <section className="card overflow-hidden"><div className="overflow-x-auto"><table className="w-full min-w-[920px] text-sm"><thead className="border-b border-slate-200 bg-slate-50 text-left text-xs text-slate-500 dark:border-slate-700 dark:bg-slate-800/60 dark:text-slate-400"><tr><th className="w-10 p-3"><input type="checkbox" checked={runs.length > 0 && selectedIds.length === runs.length} onChange={event => setSelectedIds(event.target.checked ? runs.map(run => run.id) : [])} /></th><th className="p-3">运行时间</th><th className="p-3">标的</th><th className="p-3">参数</th><th className="p-3">历史截止</th><th className="p-3">收盘 → 末期预测</th><th className="p-3">状态</th><th className="p-3 text-right">操作</th></tr></thead><tbody>{loading ? <tr><td colSpan={8} className="p-12 text-center text-slate-400"><Loader2 className="mx-auto mb-2 h-5 w-5 animate-spin" />加载中</td></tr> : runs.length === 0 ? <tr><td colSpan={8} className="p-12 text-center text-slate-400">暂无预测记录</td></tr> : runs.map(run => <tr key={run.id} className={`border-b border-slate-100 last:border-0 dark:border-slate-800 ${rerunJob?.id === run.id ? 'bg-cyan-50/60 dark:bg-cyan-500/5' : ''}`}><td className="p-3"><input type="checkbox" checked={selectedIds.includes(run.id)} onChange={event => setSelectedIds(ids => event.target.checked ? [...ids, run.id] : ids.filter(id => id !== run.id))} /></td><td className="p-3 text-xs text-slate-500">{time(run.created_at)}</td><td className="p-3"><p className="font-semibold text-slate-800 dark:text-slate-100">{run.security_name || run.symbol}</p><p className="font-mono text-xs text-slate-400">{run.symbol}</p></td><td className="p-3 text-xs text-slate-500">{run.frequency} · {run.lookback_actual || run.lookback_requested} 根 · {run.pred_len} 期<br />{run.model_key} · T {number(run.temperature, 1)} · P {number(run.top_p, 2)} · S {run.sample_count}</td><td className="p-3 font-mono text-xs text-slate-500">{run.history_end_date ? date(run.history_end_date) : '--'}</td><td className="p-3 tabular-nums">{number(run.summary.latest_close)} <span className="text-slate-400">→</span> <span className="text-cyan-600 dark:text-cyan-300">{number(run.summary.final_forecast)}</span><p className={run.summary.forecast_change_pct != null && run.summary.forecast_change_pct >= 0 ? 'text-xs text-rose-500' : 'text-xs text-emerald-500'}>{run.summary.forecast_change_pct == null ? '--' : `${run.summary.forecast_change_pct >= 0 ? '+' : ''}${number(run.summary.forecast_change_pct)}%`}</p></td><td className="p-3"><span className={`rounded-full px-2 py-1 text-xs ${rerunJob?.id === run.id ? 'bg-cyan-100 text-cyan-700 dark:bg-cyan-500/15 dark:text-cyan-300' : run.status === 'completed' ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300' : run.status === 'failed' ? 'bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300' : 'bg-blue-100 text-blue-700'}`}>{rerunJob?.id === run.id ? '重新预测中' : run.status === 'completed' ? '已完成' : run.status === 'failed' ? '失败' : '运行中'}</span></td><td className="p-3"><div className="flex justify-end gap-1"><button title="查看快照" onClick={() => void open(run.id)} disabled={Boolean(rerunJob) || busyId === run.id} className="rounded p-2 text-blue-600 hover:bg-blue-50 disabled:opacity-40 dark:text-blue-300 dark:hover:bg-blue-500/10"><Eye className="h-4 w-4" /></button><button title={rerunJob?.id === run.id ? '重新预测中' : '重新运行'} onClick={() => void rerun(run)} disabled={Boolean(rerunJob)} className="rounded p-2 text-cyan-600 hover:bg-cyan-50 disabled:cursor-wait disabled:opacity-60 dark:text-cyan-300 dark:hover:bg-cyan-500/10">{rerunJob?.id === run.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}</button><button title="删除" onClick={() => void remove(run.id)} disabled={Boolean(rerunJob) || busyId === run.id} className="rounded p-2 text-rose-500 hover:bg-rose-50 disabled:opacity-40 dark:hover:bg-rose-500/10"><Trash2 className="h-4 w-4" /></button></div></td></tr>)}</tbody></table></div><footer className="flex items-center justify-between border-t border-slate-200 p-3 text-sm text-slate-500 dark:border-slate-700"><span>共 {total} 条</span><div className="flex gap-2"><button disabled={skip === 0 || loading || Boolean(rerunJob)} onClick={() => setSkip(Math.max(0, skip - PAGE_SIZE))} className="btn-secondary px-3 py-1 text-xs">上一页</button><button disabled={skip + PAGE_SIZE >= total || loading || Boolean(rerunJob)} onClick={() => setSkip(skip + PAGE_SIZE)} className="btn-secondary px-3 py-1 text-xs">下一页</button></div></footer></section>
    </div>
}

function KronosDetail({ run, data, busy, rerunJob: _rerunJob, elapsedSeconds: _elapsedSeconds, onBack, onRerun, onExportJson, onExportCsv, onDelete }: { run: KronosPredictionRun; data: Array<{ date: string; actual?: number; forecast?: number }>; busy: boolean; rerunJob: { id: string; symbol: string; startedAt: number } | null; elapsedSeconds: number; onBack: () => void; onRerun: () => void; onExportJson: () => void; onExportCsv: () => void; onDelete: () => void }) {
    const snapshot = run.parameter_snapshot
    const request = snapshot?.request
    const market = snapshot?.market_data
    const execution = snapshot?.execution
    return <div className="space-y-6"><header className="flex flex-wrap items-start justify-between gap-4"><div><button onClick={onBack} className="mb-3 flex items-center gap-1 text-sm text-slate-500 hover:text-blue-600"><ArrowLeft className="h-4 w-4" />返回预测记录</button><p className="text-xs font-semibold uppercase tracking-[0.18em] text-cyan-600">Frozen Snapshot</p><h1 className="mt-1 text-2xl font-bold text-slate-900 dark:text-slate-100">{run.security_name || run.symbol} · 预测快照</h1><p className="mt-2 font-mono text-sm text-slate-500">{run.symbol} · 创建于 {time(run.created_at)}</p></div><div className="flex flex-wrap gap-2"><button onClick={onExportJson} className="btn-secondary flex items-center gap-2"><Download className="h-4 w-4" />JSON</button><button onClick={onExportCsv} className="btn-secondary flex items-center gap-2"><Download className="h-4 w-4" />CSV</button><button onClick={onRerun} disabled={busy} className="btn-primary flex items-center gap-2"><Play className="h-4 w-4" />{busy ? '运行中…' : '使用当前行情重新运行'}</button><button onClick={onDelete} className="btn-secondary p-2 text-rose-500"><Trash2 className="h-4 w-4" /></button></div></header>{run.status === 'failed' ? <div className="card border-rose-200 bg-rose-50 p-5 text-rose-700 dark:border-rose-900/60 dark:bg-rose-950/30 dark:text-rose-300">本次预测失败：{run.error_message || '未知错误'}</div> : <><section className="card h-[420px] p-5"><ResponsiveContainer width="100%" height="100%"><LineChart data={data}><CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.22)" vertical={false} /><XAxis dataKey="date" tickFormatter={date} minTickGap={42} tick={{ fontSize: 11, fill: '#94a3b8' }} axisLine={false} tickLine={false} /><YAxis tick={{ fontSize: 11, fill: '#94a3b8' }} axisLine={false} tickLine={false} width={56} /><Tooltip labelFormatter={label => date(String(label))} formatter={(value: number, name: string) => [number(value), name === 'actual' ? '历史收盘' : 'Kronos 预测']} contentStyle={{ borderRadius: 10, border: '1px solid #cbd5e1', backgroundColor: '#fff', color: '#334155' }} /><Line type="monotone" dataKey="actual" stroke="#3b82f6" strokeWidth={2} dot={false} connectNulls /><Line type="monotone" dataKey="forecast" stroke="#06b6d4" strokeWidth={2.5} strokeDasharray="6 4" dot={false} connectNulls /></LineChart></ResponsiveContainer></section><section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4"><Info label="历史区间" value={`${date(run.history_start_date || '')} → ${date(run.history_end_date || '')}`} /><Info label="参数" value={`${run.frequency} · ${run.lookback_actual || run.lookback_requested} 根 · ${run.pred_len} 期`} /><Info label="采样配置" value={`T ${number(run.temperature, 1)} · Top-p ${number(run.top_p, 2)} · ${run.sample_count} 次`} /><Info label="运行环境" value={`${run.model_loaded || run.model_key} · ${run.device || '--'} · ${number(run.inference_time_ms, 0)} ms`} /></section><section className="card p-5"><div className="mb-4"><p className="text-xs font-semibold uppercase tracking-[0.16em] text-cyan-600">Parameters Snapshot</p><h2 className="mt-1 text-lg font-semibold text-slate-900 dark:text-slate-100">完整参数快照</h2><p className="mt-1 text-xs text-slate-500 dark:text-slate-400">以下字段在本次运行完成后冻结保存；重新运行将创建新的快照。</p></div><div className="grid gap-4 lg:grid-cols-3"><SnapshotGroup title="请求参数" items={[['标的', request?.symbol || run.symbol], ['K 线频率', `${request?.frequency || run.frequency} (${request?.market_period || '--'})`], ['历史窗口', `${request?.lookback ?? run.lookback_requested} 根（实际 ${market?.history_candle_count ?? run.lookback_actual ?? '--'} 根）`], ['预测长度', `${request?.pred_len ?? run.pred_len} 期（实际 ${execution?.prediction_candle_count ?? run.predictions?.length ?? '--'} 期）`], ['模型', request?.model_key || run.model_key], ['Temperature (T)', number(request?.temperature ?? run.temperature, 1)], ['Top-p (P)', number(request?.top_p ?? run.top_p, 2)], ['采样次数 (S)', `${request?.sample_count ?? run.sample_count} 次`]]} /><SnapshotGroup title="行情输入" items={[['数据来源', market?.source || run.market_data_source || '--'], ['拉取区间', market ? `${date(market.query_start_date)} → ${date(market.query_end_date)}` : '--'], ['有效 K 线', market?.valid_candle_count != null ? `${market.valid_candle_count} 根` : '--'], ['实际历史区间', market ? `${date(market.history_start_date)} → ${date(market.history_end_date)}` : `${date(run.history_start_date || '')} → ${date(run.history_end_date || '')}`], ['历史 K 线数', market?.history_candle_count != null ? `${market.history_candle_count} 根` : `${run.lookback_actual || '--'} 根`]]} /><SnapshotGroup title="实际执行" items={[['加载模型', execution?.model_loaded || run.model_loaded || run.model_key], ['运行设备', execution?.device || run.device || '--'], ['推理耗时', `${number(execution?.inference_time_ms ?? run.inference_time_ms, 0)} ms`], ['预测交易日', execution?.forecast_start_date && execution?.forecast_end_date ? `${date(execution.forecast_start_date)} → ${date(execution.forecast_end_date)}` : '--'], ['交易日历', execution?.trading_calendar === 'cn_a_share' ? '中国 A 股交易日历' : execution?.trading_calendar || '--'], ['快照格式', `v${snapshot?.snapshot_format ?? run.snapshot_version}`]]} /></div></section></>}</div>
}

function Info({ label, value }: { label: string; value: string }) { return <div className="card p-4"><p className="text-xs text-slate-400">{label}</p><p className="mt-1 text-sm font-semibold text-slate-800 dark:text-slate-100">{value}</p></div> }

function SnapshotGroup({ title, items }: { title: string; items: Array<[string, string]> }) { return <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-4 dark:border-slate-700 dark:bg-slate-800/40"><h3 className="mb-3 text-sm font-semibold text-slate-800 dark:text-slate-100">{title}</h3><dl className="space-y-2.5">{items.map(([label, value]) => <div key={label} className="flex items-start justify-between gap-3 text-xs"><dt className="shrink-0 text-slate-500 dark:text-slate-400">{label}</dt><dd className="break-all text-right font-mono font-medium text-slate-700 dark:text-slate-200">{value || '--'}</dd></div>)}</dl></div> }

function RerunProgress({ symbol, elapsedSeconds }: { symbol: string; elapsedSeconds: number }) {
    return <section className="card border-cyan-200 bg-cyan-50/70 p-4 dark:border-cyan-500/30 dark:bg-cyan-500/10" role="status" aria-live="polite">
        <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-cyan-100 text-cyan-600 dark:bg-cyan-500/20 dark:text-cyan-300"><Loader2 className="h-5 w-5 animate-spin" /></div>
            <div className="min-w-0"><p className="font-semibold text-cyan-900 dark:text-cyan-100">正在重新预测 {symbol}</p><p className="mt-0.5 text-xs text-cyan-700 dark:text-cyan-200">正在读取最新行情并执行 Kronos 推理，已运行 {elapsedSeconds} 秒。完成后将自动打开新快照。</p></div>
        </div>
        <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-cyan-100 dark:bg-cyan-900/50"><div className="h-full w-1/2 animate-pulse rounded-full bg-cyan-500" /></div>
    </section>
}
