import { useCallback, useEffect, useMemo, useState } from 'react'
import {
    Activity,
    AlertCircle,
    BarChart3,
    CheckCircle2,
    Cpu,
    Gauge,
    Play,
    RefreshCw,
    Server,
    SlidersHorizontal,
    Sparkles,
    Timer,
} from 'lucide-react'
import {
    CartesianGrid,
    Line,
    LineChart,
    ResponsiveContainer,
    Tooltip,
    XAxis,
    YAxis,
} from 'recharts'

import { api } from '@/services/api'
import type {
    KlineCandle,
    KronosHealth,
    KronosKlineDataPoint,
    KronosModelInfo,
    KronosPrediction as KronosPredictionPoint,
} from '@/types'

type KronosConfig = {
    symbol: string
    frequency: 'D' | 'H' | 'min'
    lookback: number
    predLen: number
    temperature: number
    topP: number
    sampleCount: number
    model: 'small' | 'base'
}

type ChartPoint = {
    date: string
    actual?: number
    forecast?: number
}

const DEFAULT_CONFIG: KronosConfig = {
    symbol: '000001.SZ',
    frequency: 'D',
    lookback: 120,
    predLen: 30,
    temperature: 1,
    topP: 0.9,
    sampleCount: 1,
    model: 'base',
}

const FREQUENCIES: Array<{ value: KronosConfig['frequency']; label: string; period: '1d' | '5m' | '1m' }> = [
    { value: 'D', label: '日线', period: '1d' },
    { value: 'H', label: '小时', period: '5m' },
    { value: 'min', label: '分钟', period: '1m' },
]

const PRESET_SYMBOLS = [
    { symbol: '000001.SZ', label: '平安银行' },
    { symbol: '600519.SH', label: '贵州茅台' },
    { symbol: '300750.SZ', label: '宁德时代' },
]

function formatNumber(value: number | null | undefined, digits = 2) {
    if (value == null || !Number.isFinite(value)) return '--'
    return value.toLocaleString('zh-CN', { maximumFractionDigits: digits, minimumFractionDigits: digits })
}

function formatDate(value: string) {
    const date = new Date(value)
    if (Number.isNaN(date.getTime())) return value.slice(0, 10)
    return date.toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' })
}

function nextDate(dateText: string, frequency: KronosConfig['frequency'], offset: number) {
    const date = new Date(dateText)
    if (Number.isNaN(date.getTime())) return `${dateText}-${offset + 1}`
    if (frequency === 'D') date.setDate(date.getDate() + offset)
    else if (frequency === 'H') date.setHours(date.getHours() + offset)
    else date.setMinutes(date.getMinutes() + offset * 5)
    return date.toISOString()
}

function toKronosKline(candle: KlineCandle): KronosKlineDataPoint {
    return {
        open: Number(candle.open),
        high: Number(candle.high),
        low: Number(candle.low),
        close: Number(candle.close),
        volume: Number(candle.volume ?? 0),
        amount: Number(candle.amount ?? 0),
    }
}

export default function KronosPrediction() {
    const [config, setConfig] = useState<KronosConfig>(() => {
        try {
            const saved = localStorage.getItem('tradingagents-kronos-config')
            return saved ? { ...DEFAULT_CONFIG, ...JSON.parse(saved) } : DEFAULT_CONFIG
        } catch {
            return DEFAULT_CONFIG
        }
    })
    const [health, setHealth] = useState<KronosHealth | null>(null)
    const [modelInfo, setModelInfo] = useState<KronosModelInfo | null>(null)
    const [candles, setCandles] = useState<KlineCandle[]>([])
    const [predictions, setPredictions] = useState<KronosPredictionPoint[]>([])
    const [inferenceTimeMs, setInferenceTimeMs] = useState<number | null>(null)
    const [loadingService, setLoadingService] = useState(true)
    const [running, setRunning] = useState(false)
    const [switchingModel, setSwitchingModel] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const [lastRunAt, setLastRunAt] = useState<string | null>(null)

    const updateConfig = <K extends keyof KronosConfig>(key: K, value: KronosConfig[K]) => {
        setConfig(current => ({ ...current, [key]: value }))
    }

    useEffect(() => {
        try {
            localStorage.setItem('tradingagents-kronos-config', JSON.stringify(config))
        } catch {
            // Settings remain usable when browser storage is unavailable.
        }
    }, [config])

    const loadServiceInfo = useCallback(async () => {
        setLoadingService(true)
        try {
            const [nextHealth, nextInfo] = await Promise.all([api.getKronosHealth(), api.getKronosModelInfo()])
            setHealth(nextHealth)
            setModelInfo(nextInfo)
            if (nextInfo.current_model === 'small' || nextInfo.current_model === 'base') {
                setConfig(current => ({ ...current, model: nextInfo.current_model as 'small' | 'base' }))
            }
            setError(null)
        } catch (err) {
            setHealth(null)
            setModelInfo(null)
            setError(err instanceof Error ? err.message : '无法连接 Kronos 服务')
        } finally {
            setLoadingService(false)
        }
    }, [])

    // The service check is intentionally initiated after mount so the page can render immediately.
    useEffect(() => { void loadServiceInfo() }, [loadServiceInfo]) // eslint-disable-line react-hooks/set-state-in-effect

    const switchModel = async (model: 'small' | 'base') => {
        if (model === config.model || switchingModel) return
        setSwitchingModel(true)
        setError(null)
        try {
            await api.switchKronosModel(model)
            updateConfig('model', model)
            await loadServiceInfo()
        } catch (err) {
            setError(err instanceof Error ? err.message : '模型切换失败')
        } finally {
            setSwitchingModel(false)
        }
    }

    const runPrediction = async () => {
        const symbol = config.symbol.trim().toUpperCase()
        if (!symbol) {
            setError('请输入股票代码')
            return
        }
        setRunning(true)
        setError(null)
        setPredictions([])
        try {
            const selectedFrequency = FREQUENCIES.find(item => item.value === config.frequency) ?? FREQUENCIES[0]
            const end = new Date()
            const days = config.frequency === 'D' ? Math.max(config.lookback * 2, 180) : config.frequency === 'H' ? 45 : 10
            const start = new Date(end.getTime() - days * 24 * 60 * 60 * 1000)
            const response = await api.getKline(symbol, start.toISOString().slice(0, 10), end.toISOString().slice(0, 10), selectedFrequency.period)
            const source = response.candles.filter(candle => [candle.open, candle.high, candle.low, candle.close].every(value => Number.isFinite(Number(value))))
            if (source.length < 10) throw new Error('可用 K 线不足 10 根，无法进行 Kronos 预测')
            const history = source.slice(-Math.min(config.lookback, 512))
            const result = await api.predictKronos({
                klines: history.map(toKronosKline),
                pred_len: config.predLen,
                temperature: config.temperature,
                top_p: config.topP,
                sample_count: config.sampleCount,
                freq: config.frequency,
            })
            if (!result.success || !result.predictions?.length) throw new Error(result.error || 'Kronos 未返回预测结果')
            setCandles(history)
            setPredictions(result.predictions)
            setInferenceTimeMs(result.inference_time_ms)
            setHealth(current => current ? { ...current, status: 'ready' } : current)
            setLastRunAt(new Date().toLocaleString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }))
        } catch (err) {
            setError(err instanceof Error ? err.message : '预测失败，请检查服务状态')
        } finally {
            setRunning(false)
        }
    }

    const chartData = useMemo<ChartPoint[]>(() => {
        const history = candles.slice(-80).map(candle => ({ date: candle.date, actual: Number(candle.close) }))
        if (!predictions.length || !candles.length) return history
        const lastDate = candles[candles.length - 1].date
        const forecast = predictions.map((prediction, index) => ({
            date: nextDate(lastDate, config.frequency, index + 1),
            forecast: Number(prediction.close),
        }))
        return [
            ...history,
            { date: lastDate, actual: Number(candles[candles.length - 1].close), forecast: Number(predictions[0].close) },
            ...forecast.slice(1),
        ]
    }, [candles, config.frequency, predictions])

    const latestClose = candles[candles.length - 1]?.close
    const finalForecast = predictions[predictions.length - 1]?.close
    const forecastChange = latestClose && finalForecast != null ? ((finalForecast - latestClose) / latestClose) * 100 : null
    const statusReady = health?.status === 'ready'

    return (
        <div className="space-y-6">
            <header className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div>
                    <div className="flex items-center gap-3">
                        <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-cyan-100 dark:bg-cyan-500/15">
                            <Sparkles className="h-6 w-6 text-cyan-600 dark:text-cyan-300" />
                        </div>
                        <div>
                            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-cyan-600 dark:text-cyan-300">Forecast Lab</p>
                            <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">kronos预测</h1>
                        </div>
                    </div>
                    <p className="mt-3 max-w-2xl text-sm text-slate-500 dark:text-slate-400">基于 Kronos 时序模型的 OHLCVA 预测工作台，调整采样参数后即可对当前标的发起推理。</p>
                </div>
                <div className={`inline-flex items-center gap-2 self-start rounded-full border px-3 py-2 text-xs font-semibold ${statusReady ? 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-300' : 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300'}`}>
                    <span className={`h-2 w-2 rounded-full ${statusReady ? 'bg-emerald-500' : 'bg-amber-500'}`} />
                    {loadingService ? '正在连接' : statusReady ? `服务正常 · ${health?.device || 'CPU'}` : '服务待检查'}
                </div>
            </header>

            {error && (
                <div className="flex items-start gap-3 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-900/60 dark:bg-rose-950/30 dark:text-rose-300">
                    <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                    <span>{error}</span>
                </div>
            )}

            <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_340px]">
                <section className="card min-h-[520px] overflow-hidden p-0">
                    <div className="flex flex-col gap-3 border-b border-slate-200 px-5 py-4 dark:border-slate-700 sm:flex-row sm:items-center sm:justify-between">
                        <div className="flex items-center gap-2">
                            <BarChart3 className="h-5 w-5 text-blue-500" />
                            <div>
                                <h2 className="font-semibold text-slate-900 dark:text-slate-100">收盘价路径</h2>
                                <p className="text-xs text-slate-500 dark:text-slate-400">{candles.length ? `${config.symbol} · ${candles.length} 根历史 · 未来 ${predictions.length || config.predLen} 期` : '运行预测后显示历史与预测路径'}</p>
                            </div>
                        </div>
                        {lastRunAt && <span className="text-xs text-slate-400 dark:text-slate-500">最近运行 {lastRunAt}</span>}
                    </div>
                    <div className="h-[390px] px-3 pb-3 pt-5 sm:px-5">
                        {chartData.length ? (
                            <ResponsiveContainer width="100%" height="100%">
                                <LineChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 4 }}>
                                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.22)" vertical={false} />
                                    <XAxis dataKey="date" tickFormatter={formatDate} minTickGap={42} tick={{ fontSize: 11, fill: '#94a3b8' }} axisLine={false} tickLine={false} />
                                    <YAxis domain={['auto', 'auto']} tickFormatter={(value: number) => formatNumber(value, 0)} tick={{ fontSize: 11, fill: '#94a3b8' }} axisLine={false} tickLine={false} width={48} />
                                    <Tooltip labelFormatter={(label) => new Date(String(label)).toLocaleString('zh-CN')} formatter={(value: number, name: string) => [formatNumber(value), name === 'actual' ? '历史收盘' : 'Kronos 预测']} contentStyle={{ borderRadius: 10, border: '1px solid #cbd5e1', backgroundColor: '#ffffff', color: '#334155', fontSize: 12 }} labelStyle={{ color: '#1e293b', fontWeight: 600, marginBottom: 4 }} itemStyle={{ color: '#475569' }} />
                                    <Line type="monotone" dataKey="actual" stroke="#3b82f6" strokeWidth={2} dot={false} connectNulls />
                                    <Line type="monotone" dataKey="forecast" stroke="#06b6d4" strokeWidth={2.5} strokeDasharray="6 4" dot={false} connectNulls />
                                </LineChart>
                            </ResponsiveContainer>
                        ) : (
                            <div className="flex h-full flex-col items-center justify-center text-center">
                                <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-slate-100 dark:bg-slate-800"><Activity className="h-7 w-7 text-slate-400" /></div>
                                <p className="font-medium text-slate-600 dark:text-slate-300">准备好开始预测</p>
                                <p className="mt-1 text-sm text-slate-400 dark:text-slate-500">设置参数后点击右侧“运行预测”</p>
                            </div>
                        )}
                    </div>
                    <div className="grid grid-cols-2 gap-3 border-t border-slate-200 p-4 dark:border-slate-700 sm:grid-cols-4">
                        <Metric label="最新收盘" value={formatNumber(latestClose)} />
                        <Metric label="末期预测" value={formatNumber(finalForecast)} accent="cyan" />
                        <Metric label="预测变化" value={forecastChange == null ? '--' : `${forecastChange >= 0 ? '+' : ''}${formatNumber(forecastChange)}%`} accent={forecastChange != null && forecastChange >= 0 ? 'rose' : 'emerald'} />
                        <Metric label="推理耗时" value={inferenceTimeMs == null ? '--' : `${formatNumber(inferenceTimeMs, 0)} ms`} />
                    </div>
                </section>

                <aside className="card p-5">
                    <div className="mb-5 flex items-center gap-2"><SlidersHorizontal className="h-5 w-5 text-blue-500" /><h2 className="font-semibold text-slate-900 dark:text-slate-100">预测配置</h2></div>
                    <div className="space-y-5">
                        <label className="block"><span className="mb-2 block text-xs font-semibold text-slate-500 dark:text-slate-400">股票代码</span><input value={config.symbol} onChange={event => updateConfig('symbol', event.target.value.toUpperCase())} onKeyDown={event => { if (event.key === 'Enter') void runPrediction() }} placeholder="例如 000001.SZ" className="input w-full font-mono" /></label>
                        <div><span className="mb-2 block text-xs font-semibold text-slate-500 dark:text-slate-400">常用标的</span><div className="flex flex-wrap gap-2">{PRESET_SYMBOLS.map(item => <button key={item.symbol} type="button" onClick={() => updateConfig('symbol', item.symbol)} className={`rounded-md border px-2.5 py-1.5 text-xs transition-colors ${config.symbol === item.symbol ? 'border-blue-500 bg-blue-50 text-blue-600 dark:bg-blue-500/10 dark:text-blue-300' : 'border-slate-200 text-slate-500 hover:border-blue-300 dark:border-slate-700 dark:text-slate-400'}`}>{item.label}</button>)}</div></div>
                        <div><span className="mb-2 block text-xs font-semibold text-slate-500 dark:text-slate-400">数据频率</span><div className="grid grid-cols-3 gap-1 rounded-lg bg-slate-100 p-1 dark:bg-slate-800">{FREQUENCIES.map(item => <button key={item.value} type="button" onClick={() => updateConfig('frequency', item.value)} className={`rounded-md px-2 py-2 text-xs font-medium transition-colors ${config.frequency === item.value ? 'bg-white text-blue-600 shadow-sm dark:bg-slate-700 dark:text-blue-300' : 'text-slate-500 hover:text-slate-700 dark:text-slate-400'}`}>{item.label}</button>)}</div></div>
                        <RangeField label="历史窗口" value={config.lookback} min={30} max={512} step={10} suffix="根" onChange={value => updateConfig('lookback', value)} />
                        <RangeField label="预测长度" value={config.predLen} min={1} max={200} step={1} suffix="期" onChange={value => updateConfig('predLen', value)} />
                        <RangeField label="Temperature" value={config.temperature} min={0.1} max={5} step={0.1} suffix="" onChange={value => updateConfig('temperature', value)} />
                        <RangeField label="Top-p" value={config.topP} min={0} max={1} step={0.05} suffix="" onChange={value => updateConfig('topP', value)} />
                        <RangeField label="采样次数" value={config.sampleCount} min={1} max={5} step={1} suffix="次" onChange={value => updateConfig('sampleCount', value)} />
                        <div><span className="mb-2 block text-xs font-semibold text-slate-500 dark:text-slate-400">模型</span><div className="grid grid-cols-2 gap-2">{(['small', 'base'] as const).map(model => <button key={model} type="button" disabled={switchingModel} onClick={() => void switchModel(model)} className={`rounded-lg border px-3 py-2 text-left transition-colors ${config.model === model ? 'border-cyan-400 bg-cyan-50 text-cyan-700 dark:border-cyan-500/60 dark:bg-cyan-500/10 dark:text-cyan-300' : 'border-slate-200 text-slate-500 hover:border-slate-300 dark:border-slate-700 dark:text-slate-400'}`}><span className="block text-sm font-semibold">Kronos-{model}</span><span className="mt-0.5 block text-[11px]">{modelInfo?.available_models?.[model] || (model === 'base' ? '高精度' : '轻量')}{switchingModel && config.model !== model ? '' : ''}</span></button>)}</div></div>
                        <button type="button" onClick={() => void runPrediction()} disabled={running || loadingService || !statusReady} className="btn-primary flex w-full items-center justify-center gap-2 py-2.5"><Play className="h-4 w-4 fill-current" />{running ? '推理进行中…' : '运行预测'}</button>
                        <button type="button" onClick={() => void loadServiceInfo()} disabled={loadingService} className="flex w-full items-center justify-center gap-2 rounded-lg px-3 py-2 text-xs font-medium text-slate-500 transition-colors hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800"><RefreshCw className={`h-3.5 w-3.5 ${loadingService ? 'animate-spin' : ''}`} />刷新服务状态</button>
                    </div>
                </aside>
            </div>

            <section className="grid gap-4 md:grid-cols-3">
                <ServiceCard icon={Server} label="服务状态" value={statusReady ? 'Ready' : (health?.status || 'Offline')} detail={health ? `${health.model} · ${health.device}` : '请启动 kronos_service'} tone={statusReady ? 'green' : 'orange'} />
                <ServiceCard icon={Cpu} label="模型运行" value={config.model === 'base' ? 'Kronos-base' : 'Kronos-small'} detail={health?.vram_used_mb != null ? `显存 ${formatNumber(health.vram_used_mb, 0)} MB` : 'CPU 推理模式'} tone="blue" />
                <ServiceCard icon={Timer} label="采样策略" value={`${config.sampleCount} 次采样`} detail={`T ${formatNumber(config.temperature)} · Top-p ${formatNumber(config.topP)}`} tone="purple" />
            </section>
        </div>
    )
}

function RangeField({ label, value, min, max, step, suffix, onChange }: { label: string; value: number; min: number; max: number; step: number; suffix: string; onChange: (value: number) => void }) {
    return <label className="block"><div className="mb-1.5 flex items-center justify-between text-xs font-semibold text-slate-500 dark:text-slate-400"><span>{label}</span><span className="font-mono text-slate-700 dark:text-slate-200">{formatNumber(value, step < 1 ? 2 : 0)} {suffix}</span></div><input type="range" min={min} max={max} step={step} value={value} onChange={event => onChange(Number(event.target.value))} className="h-1.5 w-full cursor-pointer accent-blue-500" /></label>
}

function Metric({ label, value, accent = 'slate' }: { label: string; value: string; accent?: 'slate' | 'cyan' | 'rose' | 'emerald' }) {
    const colors = { slate: 'text-slate-900 dark:text-slate-100', cyan: 'text-cyan-600 dark:text-cyan-300', rose: 'text-rose-600 dark:text-rose-300', emerald: 'text-emerald-600 dark:text-emerald-300' }
    return <div className="min-w-0"><p className="truncate text-xs text-slate-400 dark:text-slate-500">{label}</p><p className={`mt-1 truncate text-sm font-semibold ${colors[accent]}`}>{value}</p></div>
}

function ServiceCard({ icon: Icon, label, value, detail, tone }: { icon: typeof Gauge; label: string; value: string; detail: string; tone: 'green' | 'orange' | 'blue' | 'purple' }) {
    const tones = { green: 'bg-emerald-100 text-emerald-600 dark:bg-emerald-500/15 dark:text-emerald-300', orange: 'bg-orange-100 text-orange-600 dark:bg-orange-500/15 dark:text-orange-300', blue: 'bg-blue-100 text-blue-600 dark:bg-blue-500/15 dark:text-blue-300', purple: 'bg-purple-100 text-purple-600 dark:bg-purple-500/15 dark:text-purple-300' }
    return <div className="card flex items-center gap-3 p-4"><div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${tones[tone]}`}><Icon className="h-5 w-5" /></div><div className="min-w-0"><p className="text-xs text-slate-500 dark:text-slate-400">{label}</p><p className="truncate text-sm font-semibold text-slate-900 dark:text-slate-100">{value}</p><p className="truncate text-xs text-slate-400 dark:text-slate-500">{detail}</p></div>{tone === 'green' && <CheckCircle2 className="ml-auto h-4 w-4 shrink-0 text-emerald-500" />}</div>
}
