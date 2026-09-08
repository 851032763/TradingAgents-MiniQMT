type SecurityLabelProps = {
    symbol: string
    name?: string | null
    className?: string
    nameClassName?: string
    symbolClassName?: string
}

export function getSecurityName(name: string | null | undefined, symbol: string): string {
    const normalized = symbol.trim().toUpperCase()
    const value = name?.trim()
    return value && value.toUpperCase() !== normalized ? value : normalized
}

export default function SecurityLabel({
    symbol,
    name,
    className = '',
    nameClassName = '',
    symbolClassName = '',
}: SecurityLabelProps) {
    const displayName = getSecurityName(name, symbol)

    return (
        <div className={`min-w-0 ${className}`}>
            <p className={`truncate font-medium text-slate-900 dark:text-slate-100 ${nameClassName}`}>{displayName}</p>
            <p className={`mt-0.5 font-mono text-xs text-slate-400 dark:text-slate-500 ${symbolClassName}`}>{symbol}</p>
        </div>
    )
}
