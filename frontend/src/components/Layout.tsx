import { ReactNode, useEffect, useState } from 'react'
import Sidebar from './Sidebar'
import Header from './Header'

interface LayoutProps {
    children: ReactNode
}

export default function Layout({ children }: LayoutProps) {
    const [isSidebarPinned, setIsSidebarPinned] = useState(() => {
        try {
            return localStorage.getItem('ta-sidebar-pinned') === '1'
        } catch {
            return false
        }
    })

    useEffect(() => {
        try {
            localStorage.setItem('ta-sidebar-pinned', isSidebarPinned ? '1' : '0')
        } catch {
            // Keep the control usable when browser storage is unavailable.
        }
    }, [isSidebarPinned])

    return (
        <div className="min-h-screen bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100">
            <Sidebar isPinned={isSidebarPinned} onPinnedChange={setIsSidebarPinned} />
            <div className={`min-h-screen flex flex-col transition-[margin] duration-300 ${isSidebarPinned ? 'ml-56' : 'ml-16'}`}>
                <Header />
                <main className="flex-1 p-6 bg-slate-50 dark:bg-gradient-to-br dark:from-slate-900 dark:via-slate-900/95 dark:to-slate-800">
                    {children}
                </main>
            </div>
        </div>
    )
}
