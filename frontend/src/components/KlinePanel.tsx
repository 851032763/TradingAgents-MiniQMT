import { useEffect, useMemo, useRef, useState } from 'react'
import { BusinessDay, CandlestickData, CandlestickSeries, ColorType, IChartApi, ISeriesApi, MouseEventParams, UTCTimestamp, createChart } from 'lightweight-charts'
import { Activity, CandlestickChart, Radio, WifiOff } from 'lucide-react'
import { api } from '@/services/api'
import type { KlineCandle, KlineResponse } from '@/types'

interface KlinePanelProps { symbol: string; onSymbolChange?: (symbol: string) => void }
type Period = '1d' | '5m' | '1m'
type ChartTime = BusinessDay | UTCTimestamp

function toDateText(date: Date): string {
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}
function toBusinessDay(value: string): BusinessDay | null {
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value)
    return m ? { year: Number(m[1]), month: Number(m[2]), day: Number(m[3]) } : null
}
function toChartTime(value: string, period: Period): ChartTime | null {
    if (period === '1d') return toBusinessDay(value.slice(0, 10))
    const parsed = Date.parse(value.includes('T') ? value : value.replace(' ', 'T'))
    return Number.isFinite(parsed) ? Math.floor(parsed / 1000) as UTCTimestamp : null
}
function formatMinuteDate(value: string | number): string {
    const date = typeof value === 'number' ? new Date(value * 1000) : new Date(value.includes('T') ? value : value.replace(' ', 'T'))
    if (!Number.isFinite(date.getTime())) return String(value)
    return `${date.getFullYear()}/${String(date.getMonth() + 1).padStart(2, '0')}/${String(date.getDate()).padStart(2, '0')} ${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`
}
function formatChartTime(value: BusinessDay | UTCTimestamp): string {
    if (typeof value === 'object') return `${value.year}/${String(value.month).padStart(2, '0')}/${String(value.day).padStart(2, '0')} 00:00`
    return formatMinuteDate(Number(value))
}
function chartKey(time: ChartTime): string {
    return typeof time === 'object' ? `${time.year}-${String(time.month).padStart(2, '0')}-${String(time.day).padStart(2, '0')}` : String(time)
}
function candleTime(candle: KlineCandle, period: Period): string {
    const time = toChartTime(candle.date, period)
    return time == null ? '' : chartKey(time)
}
function lastCandle(items: KlineCandle[]): KlineCandle | null { return items.length ? items[items.length - 1] : null }
const SYMBOL_NAME_MAP: Record<string, string> = { '000001.SH': '上证指数', '399001.SZ': '深证成指', '399006.SZ': '创业板指', '000300.SH': '沪深300', '000905.SH': '中证500', '000852.SH': '中证1000', '300750.SZ': '宁德时代', '600406.SH': '国电南瑞', '510300.SH': '沪深300ETF' }
function getDisplayName(symbol: string): string { const value = symbol.toUpperCase(); return SYMBOL_NAME_MAP[value] ? `${SYMBOL_NAME_MAP[value]}（${value}）` : value }
function formatNumber(value?: number | null, digits = 2): string { if (value == null || !Number.isFinite(value)) return '--'; return new Intl.NumberFormat('zh-CN', { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(value) }
function formatVolume(value?: number | null): string { if (value == null || !Number.isFinite(value)) return '--'; if (Math.abs(value) >= 1e8) return `${formatNumber(value / 1e8, 2)}亿`; if (Math.abs(value) >= 1e4) return `${formatNumber(value / 1e4, 2)}万`; return formatNumber(value, 0) }
const INDEX_PRESETS = [{ symbol: '000001.SH', label: '上证指数' }, { symbol: '399001.SZ', label: '深证成指' }, { symbol: '399006.SZ', label: '创业板指' }, { symbol: '000688.SH', label: '科创50' }, { symbol: '899050.BJ', label: '北证50' }] as const
const PERIODS: Array<{ value: Period; label: string }> = [{ value: '1d', label: '日线' }, { value: '5m', label: '5分钟' }, { value: '1m', label: '1分钟' }]

export default function KlinePanel({ symbol, onSymbolChange }: KlinePanelProps) {
    const containerRef = useRef<HTMLDivElement | null>(null)
    const chartRef = useRef<IChartApi | null>(null)
    const seriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
    const candlesRef = useRef<KlineCandle[]>([])
    const [period, setPeriod] = useState<Period>('1d')
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const [status, setStatus] = useState<string | null>(null)
    const [isDark, setIsDark] = useState(document.documentElement.classList.contains('dark'))
    const [candles, setCandles] = useState<KlineCandle[]>([])
    const [activeCandle, setActiveCandle] = useState<KlineCandle | null>(null)
    const [minuteUnavailable, setMinuteUnavailable] = useState(false)
    const [realtimeLive, setRealtimeLive] = useState(false)
    const range = useMemo(() => { const end = new Date(); const days = period === '1d' ? 180 : period === '5m' ? 30 : 7; return { start: toDateText(new Date(end.getTime() - days * 86400000)), end: toDateText(end) } }, [period])

    useEffect(() => { const observer = new MutationObserver(() => setIsDark(document.documentElement.classList.contains('dark'))); observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] }); return () => observer.disconnect() }, [])
    useEffect(() => {
        if (!containerRef.current) return
        const textColor = isDark ? '#94a3b8' : '#475569'; const gridColor = isDark ? 'rgba(51, 65, 85, 0.6)' : 'rgba(203, 213, 225, 0.6)'
        const chart = createChart(containerRef.current, { layout: { background: { type: ColorType.Solid, color: 'transparent' }, textColor, attributionLogo: false }, localization: { locale: 'zh-CN', dateFormat: 'yyyy/MM/dd', timeFormatter: (time: BusinessDay | UTCTimestamp) => period === '1d' ? formatChartTime(time).slice(0, 10) : formatChartTime(time) }, width: containerRef.current.clientWidth, height: containerRef.current.clientHeight, grid: { vertLines: { color: gridColor }, horzLines: { color: gridColor } }, rightPriceScale: { borderColor: isDark ? '#334155' : '#cbd5e1' }, timeScale: { borderColor: isDark ? '#334155' : '#cbd5e1', timeVisible: period !== '1d', rightOffset: 6, tickMarkFormatter: (time: BusinessDay | string | number) => { if (typeof time === 'object') return `${time.year}/${String(time.month).padStart(2, '0')}/${String(time.day).padStart(2, '0')}`; if (typeof time === 'number' && period !== '1d') return formatMinuteDate(time); return String(time) } }, crosshair: { vertLine: { color: isDark ? 'rgba(59, 130, 246, 0.35)' : 'rgba(59, 130, 246, 0.25)' }, horzLine: { color: isDark ? 'rgba(59, 130, 246, 0.35)' : 'rgba(59, 130, 246, 0.25)' } } })
        const series = chart.addSeries(CandlestickSeries, { upColor: '#ef4444', downColor: '#22c55e', wickUpColor: '#ef4444', wickDownColor: '#22c55e', borderVisible: false }); chartRef.current = chart; seriesRef.current = series
        const handleCrosshairMove = (param: MouseEventParams) => { if (!param.time || !seriesRef.current) { setActiveCandle(lastCandle(candlesRef.current)); return }; const pointData = param.seriesData.get(seriesRef.current) as CandlestickData<ChartTime> | undefined; if (pointData) { const key = chartKey(pointData.time); setActiveCandle(candlesRef.current.find(c => candleTime(c, period) === key) ?? null) } }
        chart.subscribeCrosshairMove(handleCrosshairMove); const handleDblClick = () => chartRef.current?.timeScale().fitContent(); containerRef.current.addEventListener('dblclick', handleDblClick); const onResize = () => chartRef.current?.applyOptions({ width: containerRef.current?.clientWidth ?? 0, height: containerRef.current?.clientHeight ?? 0 }); window.addEventListener('resize', onResize)
        return () => { window.removeEventListener('resize', onResize); containerRef.current?.removeEventListener('dblclick', handleDblClick); chart.unsubscribeCrosshairMove(handleCrosshairMove); chart.remove(); chartRef.current = null; seriesRef.current = null }
    }, [isDark, period])
    useEffect(() => {
        let cancelled = false
        const load = async () => {
            setLoading(true); setError(null); setStatus(period === '1d' ? '正在加载 K 线数据…' : '本地暂无对应分钟数据，正在通过 miniQMT 下载…')
            try {
                const response: KlineResponse = await api.getKline(symbol, range.start, range.end, period); if (cancelled) return
                const next = response.candles ?? []; const data: CandlestickData<ChartTime>[] = next.flatMap((c) => { const time = toChartTime(c.date, period); const open = Number(c.open), high = Number(c.high), low = Number(c.low), close = Number(c.close); return time != null && [open, high, low, close].every(Number.isFinite) ? [{ time, open, high, low, close }] : [] })
                candlesRef.current = next; setCandles(next); setActiveCandle(lastCandle(next)); seriesRef.current?.setData(data); chartRef.current?.timeScale().fitContent(); setMinuteUnavailable(period !== '1d' && !!response.degraded); setStatus(response.message ?? (period === '1d' ? null : response.realtime_supported ? '正在连接实时行情…' : '当前数据源仅支持分钟历史数据，暂不支持实时行情')); if (!data.length && !response.degraded) setError(period === '1d' ? '日线行情加载失败，请稍后重试' : '暂无对应周期 K 线数据')
            } catch (e) { if (cancelled) return; setError(period === '1d' ? '日线行情加载失败，请稍后重试' : (e instanceof Error ? e.message : '行情数据加载失败，请重试')); setCandles([]); candlesRef.current = []; setActiveCandle(null); seriesRef.current?.setData([]); if (period !== '1d') setMinuteUnavailable(true) } finally { if (!cancelled) setLoading(false) }
        }; load(); return () => { cancelled = true }
    }, [range.end, range.start, symbol, period])
    useEffect(() => {
        if (minuteUnavailable) return
        const source = new EventSource(api.getKlineStreamUrl(symbol, period))
        const onStatus = (event: MessageEvent<string>) => { const payload = JSON.parse(event.data) as { status?: string; message?: string; last_updated?: string }; if (payload.status === 'live') { setRealtimeLive(true); setStatus(`实时 · ${payload.last_updated ? formatMinuteDate(payload.last_updated) : ''}`) } else { setRealtimeLive(false); setStatus(payload.message ?? '实时行情已中断') } }
        const onCandle = (event: MessageEvent<string>) => { const update = JSON.parse(event.data) as KlineCandle; const next = [...candlesRef.current]; const index = next.findIndex(c => c.date === update.date); const merged = index >= 0 ? period === '1d' ? { ...next[index], ...update } : { ...next[index], ...update, open: next[index].open, high: Math.max(next[index].high, update.high), low: Math.min(next[index].low, update.low) } : update; if (index >= 0) next[index] = merged; else next.push(merged); next.sort((a, b) => a.date.localeCompare(b.date)); candlesRef.current = next; setCandles(next); setActiveCandle(lastCandle(next)); const time = toChartTime(merged.date, period); if (time != null) seriesRef.current?.update({ time, open: Number(merged.open), high: Number(merged.high), low: Number(merged.low), close: Number(merged.close) }) }
        source.addEventListener('status', onStatus as EventListener); source.addEventListener('candle.update', onCandle as EventListener); source.onerror = () => { setRealtimeLive(false); setStatus('实时行情连接已断开，正在尝试重连…') }; return () => { source.close(); setRealtimeLive(false) }
    }, [symbol, period, minuteUnavailable])

    const panelCandle = activeCandle ?? lastCandle(candles); const panelChange = panelCandle?.change ?? (panelCandle ? panelCandle.close - panelCandle.open : null); const panelChangePercent = panelCandle?.change_percent ?? (panelCandle && panelCandle.open !== 0 ? (panelChange! / panelCandle.open) * 100 : null); const isUp = (panelChange ?? 0) >= 0; const compactChangePercent = panelChangePercent == null ? '--' : `${panelChangePercent >= 0 ? '+' : ''}${formatNumber(panelChangePercent)}%`
    return <section className="card h-full flex flex-col overflow-hidden">
        <div className="flex items-center justify-between mb-3 shrink-0"><div className="min-w-0 flex items-center gap-3"><CandlestickChart className="w-5 h-5 text-cyan-500" /><div className="min-w-0 flex flex-wrap items-center gap-x-3 gap-y-1"><h2 className="truncate text-lg font-semibold text-slate-900 dark:text-slate-100">{getDisplayName(symbol)} K线</h2><div className="flex items-center gap-1">{PERIODS.map(item => <button key={item.value} disabled={item.value !== '1d' && minuteUnavailable} onClick={() => setPeriod(item.value)} className={`text-xs px-2 py-1 rounded border transition-colors ${item.value === period ? 'border-blue-500 text-blue-500 bg-blue-50 dark:bg-blue-500/10' : item.value !== '1d' && minuteUnavailable ? 'border-slate-200 dark:border-slate-700 text-slate-400 opacity-50 cursor-not-allowed' : 'border-slate-200 dark:border-slate-600 text-slate-600 dark:text-slate-400 hover:border-slate-400'}`}>{item.label}</button>)}</div>{realtimeLive && <span className="inline-flex items-center gap-1 text-xs text-red-500"><Radio className="w-3 h-3" />实时</span>}<div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs"><span className="text-slate-500 dark:text-slate-400">{panelCandle ? (period === '1d' ? panelCandle.date.replace(/-/g, '/') : formatMinuteDate(panelCandle.date)) : '--'}</span><span className={`font-medium ${isUp ? 'text-red-500' : 'text-emerald-500'}`}>收盘 {formatNumber(panelCandle?.close)}</span><span className="text-slate-500 dark:text-slate-400">开盘 {formatNumber(panelCandle?.open)}</span><span className={`font-medium ${isUp ? 'text-red-500' : 'text-emerald-500'}`}>{compactChangePercent}</span><span className="text-slate-500 dark:text-slate-400">高/低 {formatNumber(panelCandle?.high)} / {formatNumber(panelCandle?.low)}</span><span className="text-slate-500 dark:text-slate-400">量 {formatVolume(panelCandle?.volume)}</span><span className="text-slate-500 dark:text-slate-400">换手 {panelCandle?.turnover_rate == null ? '--' : `${formatNumber(panelCandle.turnover_rate)}%`}</span></div></div></div><div className="flex items-center gap-1.5">{INDEX_PRESETS.map(item => <button key={item.symbol} onClick={() => onSymbolChange?.(item.symbol)} className={`text-xs px-2 py-1 rounded border transition-colors ${item.symbol === symbol ? 'border-blue-500 text-blue-500 bg-blue-50 dark:bg-blue-500/10' : 'border-slate-200 dark:border-slate-600 text-slate-600 dark:text-slate-400 hover:text-slate-900 hover:border-slate-400'}`}>{item.label}</button>)}</div></div>
        <div className="relative flex-1 min-h-0 rounded-md border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 overflow-hidden"><div ref={containerRef} className="absolute inset-0" />{loading && <div className="absolute right-3 top-3 text-xs px-2 py-1 rounded bg-white/90 dark:bg-slate-800/90 text-slate-600 dark:text-slate-400 flex items-center gap-1"><Activity className="w-3 h-3 animate-pulse" />{status ?? '正在加载 K 线数据…'}</div>}{!loading && status && <div className="absolute left-3 top-3 max-w-[80%] text-xs px-2 py-1 rounded bg-white/90 dark:bg-slate-800/90 text-orange-500 flex items-center gap-1"><WifiOff className="w-3 h-3" />{status}</div>}{error && <div className="absolute left-3 bottom-3 text-xs px-2 py-1 rounded bg-white/90 dark:bg-slate-800/90 text-orange-500">{error}</div>}{minuteUnavailable && period !== '1d' && <button onClick={() => setPeriod('1d')} className="absolute right-3 bottom-3 text-xs px-2.5 py-1 rounded border border-blue-500 text-blue-500 bg-white/90 dark:bg-slate-800/90">切换至日线</button>}</div>
    </section>
}
