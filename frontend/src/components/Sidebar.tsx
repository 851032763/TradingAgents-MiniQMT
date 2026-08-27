import { useState } from 'react'
import { NavLink } from 'react-router-dom'
import { PanelLeftClose, PanelLeftOpen, TrendingUp } from 'lucide-react'

import { navItems } from '@/components/sidebarNav'

const buildDate = __APP_BUILD_DATE__
const buildCommit = __APP_BUILD_COMMIT__
const buildVersion = __APP_BUILD_VERSION__

interface SidebarProps {
    isPinned: boolean
    onPinnedChange: (isPinned: boolean) => void
}

export default function Sidebar({ isPinned, onPinnedChange }: SidebarProps) {
    const [isHovered, setIsHovered] = useState(false)
    const isExpanded = isPinned || isHovered
    const togglePinned = () => onPinnedChange(!isPinned)

    return (
        <aside
            className={`fixed left-0 top-0 h-full bg-slate-900/95 backdrop-blur-md border-r border-slate-700 flex flex-col z-50 transition-all duration-300 ${isExpanded ? 'w-56' : 'w-16'
                }`}
            onMouseEnter={() => setIsHovered(true)}
            onMouseLeave={() => setIsHovered(false)}
        >
            {/* Logo */}
            <div className={`h-16 flex items-center border-b border-slate-700 px-2 ${isExpanded ? 'justify-between' : 'justify-center'}`}>
                <div className="flex items-center gap-3">
                    <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-blue-500 via-purple-500 to-cyan-400 flex items-center justify-center shadow-lg shadow-blue-500/30 flex-shrink-0">
                        <TrendingUp className="w-5 h-5 text-white" />
                    </div>
                    {isExpanded && (
                        <span className="font-bold text-base bg-gradient-to-r from-blue-400 via-purple-400 to-cyan-400 bg-clip-text text-transparent whitespace-nowrap">
                            TradingAgents
                        </span>
                    )}
                </div>
                {isExpanded && (
                    <button
                        type="button"
                        onClick={togglePinned}
                        aria-label={isPinned ? '取消固定侧边栏' : '固定侧边栏'}
                        aria-pressed={isPinned}
                        title={isPinned ? '取消固定侧边栏' : '固定侧边栏'}
                        className={`grid h-8 w-8 shrink-0 place-items-center rounded-md transition-colors focus:outline-none focus:ring-2 focus:ring-blue-400/70 ${isPinned
                            ? 'bg-blue-500/20 text-blue-300 hover:bg-blue-500/30'
                            : 'text-slate-400 hover:bg-slate-800 hover:text-slate-100'
                            }`}
                    >
                        {isPinned ? <PanelLeftClose className="h-4 w-4" /> : <PanelLeftOpen className="h-4 w-4" />}
                    </button>
                )}
            </div>

            {/* Navigation */}
            <nav className="flex-1 py-4 px-2 space-y-2">
                {navItems.map((item) => (
                    <NavLink
                        key={item.path}
                        to={item.path}
                        className={({ isActive }) =>
                            `flex items-center gap-3 px-3 py-3 rounded-xl transition-all duration-200 ${isActive
                                ? 'bg-gradient-to-r from-blue-500/20 to-purple-500/20 text-blue-400 border border-blue-500/30'
                                : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-200'
                            }`
                        }
                    >
                        <item.icon className="w-5 h-5 flex-shrink-0" />
                        {isExpanded && (
                            <span className="font-medium text-sm whitespace-nowrap">{item.label}</span>
                        )}
                    </NavLink>
                ))}
            </nav>

            {/* Footer */}
            <div className="p-3 border-t border-slate-700">
                {isExpanded ? (
                    <div className="text-xs text-slate-500 text-center">
                        <p className="text-slate-400 text-sm font-medium">TradingAgents</p>
                        <p className="mt-0.5">多智能体投研系统</p>
                        <p className="mt-1 font-mono text-[11px] text-slate-400">{buildVersion}</p>
                        <p className="mt-0.5 text-[10px] text-slate-500">{buildDate} · {buildCommit}</p>
                    </div>
                ) : (
                    <button
                        type="button"
                        onClick={togglePinned}
                        aria-label="固定侧边栏"
                        aria-pressed={false}
                        title="固定侧边栏"
                        className="grid h-8 w-8 place-items-center rounded-md text-slate-400 transition-colors hover:bg-slate-800 hover:text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-400/70"
                    >
                        <PanelLeftOpen className="h-4 w-4" />
                    </button>
                )}
            </div>
        </aside>
    )
}
