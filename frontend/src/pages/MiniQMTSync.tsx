import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
    AlertCircle,
    BadgeCheck,
    CheckCircle2,
    ChevronDown,
    CircleDashed,
    Database,
    Download,
    FileBarChart2,
    Loader2,
    RefreshCw,
    Search,
    ShieldCheck,
    XCircle,
} from 'lucide-react'

import { api } from '@/services/api'
import type { MiniQMTDataTypeStat, MiniQMTSyncState, StockSearchResult } from '@/types'

const ALL_TYPES = ['market', 'financial', 'capital_holder', 'instrument', 'etf']

const emptyState: MiniQMTSyncState = {
    status: 'idle',
    message: '正在读取本地同步状态',
    selected_types: [],
    progress: { completed: 0, total: 0 },
    errors: [],
    data_types: [],
}

function formatDate(value?: string | null) {
    if (!value) return '未记录'
    const parsed = new Date(value)
    return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString('zh-CN', { hour12: false })
}

function formatDateOnly(value?: string | null) {
    return value || '未记录'
}

function formatTime(value: Date) {
    return value.toLocaleTimeString('zh-CN', { hour12: false })
}

function stateFingerprint(state: MiniQMTSyncState) {
    return JSON.stringify({
        status: state.status,
        message: state.message,
        started_at: state.started_at,
        finished_at: state.finished_at,
        progress: state.progress,
        errors: state.errors,
        data_types: state.data_types.map(item => ({ key: item.key, statistics: item.statistics })),
    })
}

function StatusPill({ status }: { status: string }) {
    const labels: Record<string, string> = {
        idle: '等待同步', inspecting: '盘点本地缓存', running: '同步中', completed: '已完成', failed: '同步失败',
        complete: '已缓存', missing: '未发现', unsupported: '当前版本不支持', unknown: '待确认',
    }
    const colors: Record<string, string> = {
        running: 'border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-500/30 dark:bg-blue-500/10 dark:text-blue-300',
        inspecting: 'border-cyan-200 bg-cyan-50 text-cyan-700 dark:border-cyan-500/30 dark:bg-cyan-500/10 dark:text-cyan-300',
        completed: 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-300',
        complete: 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-300',
        failed: 'border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-300',
        missing: 'border-slate-200 bg-slate-50 text-slate-600 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-300',
        unsupported: 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300',
        unknown: 'border-slate-200 bg-slate-50 text-slate-600 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-300',
    }
    return <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-medium ${colors[status] || colors.idle}`}>{labels[status] || status}</span>
}

function DataTypeCard({ item, checked, onToggle, disabled }: {
    item: MiniQMTDataTypeStat
    checked: boolean
    onToggle: () => void
    disabled: boolean
}) {
    const stats = item.statistics || {}
    return (
        <label className={`relative block cursor-pointer rounded-lg border p-4 transition-colors ${checked
            ? 'border-blue-400 bg-blue-50/70 dark:border-blue-500/60 dark:bg-blue-500/10'
            : 'border-slate-200 bg-white hover:border-slate-300 dark:border-slate-700 dark:bg-slate-800/60 dark:hover:border-slate-600'
        } ${disabled ? 'cursor-not-allowed opacity-60' : ''}`}>
            <input className="sr-only" type="checkbox" checked={checked} onChange={onToggle} disabled={disabled} />
            <div className="flex items-start justify-between gap-3">
                <div>
                    <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">{item.label}</p>
                    <p className="mt-1 text-xs leading-5 text-slate-500 dark:text-slate-400">{item.detail}</p>
                </div>
                <span className={`grid h-5 w-5 shrink-0 place-items-center rounded border ${checked ? 'border-blue-500 bg-blue-500 text-white' : 'border-slate-300 dark:border-slate-600'}`}>
                    {checked && <CheckCircle2 className="h-3.5 w-3.5" />}
                </span>
            </div>
            <div className="mt-4 flex items-center justify-between text-xs">
                <span className="text-slate-500 dark:text-slate-400">已覆盖 {stats.symbols || 0} 个证券</span>
                {stats.failed ? <span className="text-rose-600 dark:text-rose-300">{stats.failed} 个失败</span> : <span className="text-emerald-600 dark:text-emerald-300">状态正常</span>}
            </div>
            <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">{stats.start_date && stats.end_date ? `${stats.start_date} 至 ${stats.end_date}` : '尚无缓存日期记录'}</p>
        </label>
    )
}

export default function MiniQMTSync() {
    const [state, setState] = useState<MiniQMTSyncState>(emptyState)
    const [selectedTypes, setSelectedTypes] = useState<string[]>(ALL_TYPES)
    const [starting, setStarting] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const [symbolQuery, setSymbolQuery] = useState('')
    const [searchResults, setSearchResults] = useState<StockSearchResult[]>([])
    const [showResults, setShowResults] = useState(false)
    const [inspecting, setInspecting] = useState(false)
    const [refreshing, setRefreshing] = useState(false)
    const [lastStatusReadAt, setLastStatusReadAt] = useState<Date | null>(null)
    const [refreshFeedback, setRefreshFeedback] = useState<string | null>(null)
    const stateRef = useRef(state)

    useEffect(() => {
        stateRef.current = state
    }, [state])

    const loadStatus = useCallback(async (symbol?: string, showFeedback = false) => {
        if (showFeedback) {
            setRefreshing(true)
            setRefreshFeedback('正在读取 MiniQMT 最新状态...')
        }
        try {
            const next = await api.getMiniQMTSyncStatus(symbol)
            const changed = stateFingerprint(next) !== stateFingerprint(stateRef.current)
            setState(next)
            setError(null)
            setLastStatusReadAt(new Date())
            if (!symbol && next.selected_types.length > 0) setSelectedTypes(next.selected_types)
            if (showFeedback) setRefreshFeedback(changed ? '状态已刷新，检测到新的任务信息' : '状态已刷新，任务信息暂无变化')
        } catch (err) {
            const message = err instanceof Error ? err.message : '无法读取 MiniQMT 同步状态'
            setError(message)
            if (showFeedback) setRefreshFeedback('状态刷新失败')
        } finally {
            if (showFeedback) setRefreshing(false)
        }
    }, [])

    useEffect(() => { void loadStatus() }, [loadStatus])

    useEffect(() => {
        if (state.status !== 'running' && state.status !== 'inspecting') return undefined
        const id = window.setInterval(() => { void loadStatus() }, 1500)
        return () => window.clearInterval(id)
    }, [loadStatus, state.status])

    useEffect(() => {
        const query = symbolQuery.trim()
        if (query.length < 2 || /^[0-9.]+$/.test(query)) {
            setSearchResults([])
            return undefined
        }
        const timer = window.setTimeout(async () => {
            try {
                const data = await api.searchStocks(query)
                setSearchResults(data.results)
                setShowResults(data.results.length > 0)
            } catch {
                setSearchResults([])
            }
        }, 250)
        return () => window.clearTimeout(timer)
    }, [symbolQuery])

    const progress = state.progress.total > 0
        ? Math.min(100, Math.round(state.progress.completed / state.progress.total * 100))
        : 0
    const busy = state.status === 'running' || state.status === 'inspecting'
    const activeDataTypes = state.data_types.length > 0
        ? state.data_types
        : ALL_TYPES.map(key => ({ key, label: key, detail: '', statistics: {} }))
    const selectedSymbol = state.selected_symbol
    const hasSymbol = symbolQuery.trim().length > 0

    const summary = useMemo(() => {
        const totals = state.data_types.reduce((acc, item) => acc + (item.statistics?.symbols || 0), 0)
        const failures = state.data_types.reduce((acc, item) => acc + (item.statistics?.failed || 0), 0)
        return { totals, failures }
    }, [state.data_types])

    const toggleType = (key: string) => {
        setSelectedTypes(current => current.includes(key) ? current.filter(item => item !== key) : [...current, key])
    }

    const startSync = async () => {
        if (selectedTypes.length === 0) {
            setError('请至少选择一种数据类型')
            return
        }
        setStarting(true)
        try {
            const next = await api.startMiniQMTSync(selectedTypes)
            setState(next)
            setError(null)
        } catch (err) {
            setError(err instanceof Error ? err.message : '无法启动同步任务')
        } finally {
            setStarting(false)
        }
    }

    const inspectSymbol = async (symbol = symbolQuery) => {
        const query = symbol.trim()
        if (!query) return
        setInspecting(true)
        setShowResults(false)
        try {
            await loadStatus(query)
        } finally {
            setInspecting(false)
        }
    }

    const chooseSymbol = (result: StockSearchResult) => {
        setSymbolQuery(result.symbol)
        setSearchResults([])
        void inspectSymbol(result.symbol)
    }

    return (
        <div className="mx-auto max-w-7xl space-y-6">
            <section className="flex flex-col gap-4 border-b border-slate-200 pb-6 dark:border-slate-700 lg:flex-row lg:items-end lg:justify-between">
                <div>
                    <div className="mb-2 flex items-center gap-2 text-sm font-medium text-blue-600 dark:text-blue-300"><Database className="h-4 w-4" /> 本地数据中心</div>
                    <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">MiniQMT 数据同步</h1>
                    <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500 dark:text-slate-400">集中下载并核对 MiniQMT 本地行情缓存。同步只会调用本机已连接的 MiniQMT 服务，不会上传证券数据。</p>
                </div>
                <div className="flex flex-wrap items-center gap-3">
                    <StatusPill status={state.status} />
                    <button type="button" onClick={() => void loadStatus(undefined, true)} disabled={refreshing} title="重新读取 MiniQMT 同步状态" className="inline-flex h-10 items-center gap-2 rounded-lg border border-slate-300 px-3 text-sm font-medium text-slate-600 transition-colors hover:bg-slate-100 disabled:cursor-wait disabled:opacity-50 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-800">
                        <RefreshCw className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />
                        <span>{refreshing ? '刷新中' : '刷新状态'}</span>
                    </button>
                    <button type="button" onClick={() => void startSync()} disabled={starting || busy || selectedTypes.length === 0} className="btn-primary inline-flex h-10 items-center gap-2 whitespace-nowrap">
                        {starting || busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
                        {state.status === 'inspecting' ? '正在盘点缓存' : state.status === 'running' ? '正在同步' : '一键同步最新缓存'}
                    </button>
                </div>
            </section>

            {error && <div className="flex items-start gap-3 rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-300"><AlertCircle className="mt-0.5 h-4 w-4 shrink-0" /><span>{error}</span></div>}

            <div className="flex min-h-5 items-center justify-end gap-2 text-xs" aria-live="polite">
                {refreshFeedback && <span className={refreshFeedback === '状态刷新失败' ? 'text-rose-600 dark:text-rose-300' : 'text-emerald-600 dark:text-emerald-300'}>{refreshFeedback}</span>}
                {lastStatusReadAt && <span className="text-slate-500 dark:text-slate-400">最后读取 {formatTime(lastStatusReadAt)}</span>}
            </div>

            <section className="grid gap-4 md:grid-cols-3">
                <div className="card p-5"><p className="text-xs font-medium text-slate-500 dark:text-slate-400">缓存记录</p><p className="mt-2 text-2xl font-semibold text-slate-900 dark:text-slate-100">{summary.totals}</p><p className="mt-1 text-xs text-slate-500 dark:text-slate-400">按数据类型累计的已覆盖证券</p></div>
                <div className="card p-5"><p className="text-xs font-medium text-slate-500 dark:text-slate-400">最近完成</p><p className="mt-2 text-base font-semibold text-slate-900 dark:text-slate-100">{formatDate(state.finished_at)}</p><p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{state.scope === 'selected' ? '指定证券同步' : '市场范围同步'}</p></div>
                <div className="card p-5"><p className="text-xs font-medium text-slate-500 dark:text-slate-400">异常项</p><p className={`mt-2 text-2xl font-semibold ${summary.failures ? 'text-rose-600 dark:text-rose-300' : 'text-emerald-600 dark:text-emerald-300'}`}>{summary.failures}</p><p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{summary.failures ? '请查看页面底部的同步日志' : '当前同步记录无异常'}</p></div>
            </section>

            <section className="card p-5">
                <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center"><div><h2 className="font-semibold text-slate-900 dark:text-slate-100">同步范围</h2><p className="mt-1 text-sm text-slate-500 dark:text-slate-400">页面会自动盘点已有日线缓存；财务、股东和 ETF 等专项资料会在个股查询时只读核对。</p></div><button type="button" onClick={() => setSelectedTypes(selectedTypes.length === ALL_TYPES.length ? [] : ALL_TYPES)} disabled={busy} className="text-sm font-medium text-blue-600 hover:text-blue-700 disabled:opacity-50 dark:text-blue-300">{selectedTypes.length === ALL_TYPES.length ? '取消全选' : '全选'}</button></div>
                <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
                    {activeDataTypes.map(item => <DataTypeCard key={item.key} item={item} checked={selectedTypes.includes(item.key)} onToggle={() => toggleType(item.key)} disabled={busy} />)}
                </div>
            </section>

            <section className="grid gap-6 xl:grid-cols-[minmax(0,1.45fr)_minmax(300px,0.9fr)]">
                <div className="card p-5">
                    <div className="flex items-center justify-between gap-4"><div><h2 className="font-semibold text-slate-900 dark:text-slate-100">下载进度</h2><p className="mt-1 text-sm text-slate-500 dark:text-slate-400">{state.message}</p></div><span className="font-mono text-sm font-medium text-slate-700 dark:text-slate-200">{state.progress.completed} / {state.progress.total}</span></div>
                    <div className="mt-5 h-2 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-700"><div className="h-full rounded-full bg-blue-500 transition-[width] duration-500" style={{ width: `${progress}%` }} /></div>
                    <div className="mt-3 flex items-center justify-between text-xs text-slate-500 dark:text-slate-400"><span>{state.progress.current ? `当前：${state.progress.current}` : '等待任务开始'}</span><span>{progress}%</span></div>
                    <div className="mt-6 flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-slate-100 pt-4 text-xs text-slate-500 dark:border-slate-700 dark:text-slate-400">
                        {state.started_at && <span className="flex items-center gap-2"><CircleDashed className="h-3.5 w-3.5" />开始于 {formatDate(state.started_at)}</span>}
                        {lastStatusReadAt && <span>状态最后读取于 {formatTime(lastStatusReadAt)}</span>}
                    </div>
                </div>

                <div className="card p-5"><div className="flex items-center gap-2"><ShieldCheck className="h-5 w-5 text-emerald-500" /><h2 className="font-semibold text-slate-900 dark:text-slate-100">本地连接说明</h2></div><p className="mt-3 text-sm leading-6 text-slate-500 dark:text-slate-400">任务通过本机的 <code className="rounded bg-slate-100 px-1 py-0.5 text-xs dark:bg-slate-700">xtquant</code> 与正在运行的 MiniQMT 通信。历史盘点会自动识别行情和证券基础信息；财务、股东及 ETF 专项资料会在查询个股时按实际缓存逐项核对。某些专项数据还取决于终端版本和数据权限。</p></div>
            </section>

            <section className="card overflow-visible p-5">
                <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between"><div><h2 className="font-semibold text-slate-900 dark:text-slate-100">个股缓存核对</h2><p className="mt-1 text-sm text-slate-500 dark:text-slate-400">查询某只股票或 ETF 已有的数据类型、日期覆盖和完整性。</p></div><div className="relative w-full md:w-80"><Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" /><input value={symbolQuery} onChange={event => setSymbolQuery(event.target.value)} onFocus={() => searchResults.length > 0 && setShowResults(true)} onKeyDown={event => { if (event.key === 'Enter') void inspectSymbol() }} placeholder="输入代码或名称，例如 510300" className="input w-full py-2 pl-9 pr-20 text-sm" /><button type="button" onClick={() => void inspectSymbol()} disabled={!hasSymbol || inspecting} className="absolute right-1.5 top-1.5 grid h-7 w-7 place-items-center rounded-md text-slate-500 hover:bg-slate-100 disabled:opacity-40 dark:hover:bg-slate-700" title="查询本地缓存">{inspecting ? <Loader2 className="h-4 w-4 animate-spin" /> : <ChevronDown className="h-4 w-4 -rotate-90" />}</button>{showResults && <div className="absolute z-20 mt-1 max-h-64 w-full overflow-auto rounded-lg border border-slate-200 bg-white py-1 shadow-lg dark:border-slate-600 dark:bg-slate-800">{searchResults.map(result => <button key={result.symbol} type="button" onMouseDown={() => chooseSymbol(result)} className="flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-slate-50 dark:hover:bg-slate-700"><span className="font-medium text-slate-800 dark:text-slate-100">{result.name}</span><span className="font-mono text-xs text-slate-500">{result.symbol}</span></button>)}</div>}</div></div>
                {selectedSymbol ? <div className="mt-5 overflow-x-auto"><div className="mb-4 flex items-center gap-3"><span className="font-mono text-sm font-semibold text-slate-900 dark:text-slate-100">{selectedSymbol.symbol}</span>{selectedSymbol.complete ? <span className="inline-flex items-center gap-1 text-sm text-emerald-600 dark:text-emerald-300"><BadgeCheck className="h-4 w-4" />已覆盖当前同步范围</span> : <span className="inline-flex items-center gap-1 text-sm text-amber-600 dark:text-amber-300"><AlertCircle className="h-4 w-4" />数据尚未完整</span>}</div><table className="w-full min-w-[680px] text-left text-sm"><thead className="border-y border-slate-200 text-xs text-slate-500 dark:border-slate-700 dark:text-slate-400"><tr><th className="px-3 py-3 font-medium">数据类型</th><th className="px-3 py-3 font-medium">状态</th><th className="px-3 py-3 font-medium">起始日期</th><th className="px-3 py-3 font-medium">截止日期</th><th className="px-3 py-3 font-medium">说明</th></tr></thead><tbody>{selectedSymbol.types.map(item => <tr key={item.key} className="border-b border-slate-100 last:border-0 dark:border-slate-700/70"><td className="px-3 py-3 font-medium text-slate-800 dark:text-slate-200">{item.label}</td><td className="px-3 py-3"><StatusPill status={item.status} /></td><td className="px-3 py-3 font-mono text-xs text-slate-600 dark:text-slate-300">{formatDateOnly(item.start_date)}</td><td className="px-3 py-3 font-mono text-xs text-slate-600 dark:text-slate-300">{formatDateOnly(item.end_date)}</td><td className="px-3 py-3 text-xs text-slate-500 dark:text-slate-400">{item.note || item.detail}</td></tr>)}</tbody></table></div> : <div className="mt-7 flex min-h-36 flex-col items-center justify-center border-t border-dashed border-slate-200 text-center dark:border-slate-700"><FileBarChart2 className="h-7 w-7 text-slate-300 dark:text-slate-600" /><p className="mt-3 text-sm text-slate-500 dark:text-slate-400">输入证券代码或名称，查看该标的的本地缓存覆盖情况</p></div>}
            </section>

            {state.errors.length > 0 && <section className="rounded-lg border border-amber-200 bg-amber-50/70 p-5 dark:border-amber-500/30 dark:bg-amber-500/10"><div className="flex items-center gap-2 text-sm font-semibold text-amber-800 dark:text-amber-200"><XCircle className="h-4 w-4" />同步日志</div><ul className="mt-3 space-y-1.5 text-xs leading-5 text-amber-700 dark:text-amber-300">{state.errors.slice(0, 10).map((item, index) => <li key={`${index}-${item}`}>{item}</li>)}</ul></section>}
        </div>
    )
}
