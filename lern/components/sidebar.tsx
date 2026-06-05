'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import {
  LayoutDashboard,
  BookOpen,
  RotateCcw,
  Library,
  ChevronDown,
  ChevronRight
} from 'lucide-react'
import { useState } from 'react'

const modules = [
  { slug: 'a1-1', title: 'A1.1' },
  { slug: 'a1-2', title: 'A1.2' },
  { slug: 'a2-1', title: 'A2.1' },
  { slug: 'a2-2', title: 'A2.2' },
  { slug: 'b1-1', title: 'B1.1' },
  { slug: 'b1-2', title: 'B1.2' },
]

export function Sidebar() {
  const pathname = usePathname()
  const [modulesOpen, setModulesOpen] = useState(true)

  function isActive(path: string) {
    return pathname === path
  }

  function isModuleActive(slug: string) {
    return pathname.startsWith(`/dashboard/${slug}`)
  }

  return (
    <aside className="w-[260px] h-screen bg-[#fafafa] border-r border-[#e5e5e5] flex flex-col fixed left-0 top-0">
      <div className="h-16 flex items-center px-5 border-b border-[#e5e5e5]">
        <Link href="/dashboard" className="flex items-center gap-2">
          <span className="text-lg font-bold text-[#171717]">Lern</span>
          <span className="text-xs text-[#a3a3a3] font-medium">by Prognot</span>
        </Link>
      </div>

      <nav className="flex-1 overflow-y-auto py-4 px-3">
        <ul className="space-y-1">
          <li>
            <Link
              href="/dashboard"
              className={`flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors ${
                isActive('/dashboard')
                  ? 'bg-white text-[#171717] font-medium border border-[#e5e5e5]'
                  : 'text-[#737373] hover:text-[#171717] hover:bg-[#f5f5f5]'
              }`}
            >
              <LayoutDashboard size={16} />
              Dashboard
            </Link>
          </li>

          <li className="pt-4">
            <button
              onClick={() => setModulesOpen(!modulesOpen)}
              className="flex items-center gap-2 px-3 py-1 text-xs font-semibold text-[#a3a3a3] uppercase tracking-wider w-full"
            >
              {modulesOpen ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
              Modules
            </button>
            {modulesOpen && (
              <ul className="mt-1 space-y-0.5">
                {modules.map(m => (
                  <li key={m.slug}>
                    <Link
                      href={`/dashboard/${m.slug}`}
                      className={`flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors ${
                        isModuleActive(m.slug)
                          ? 'bg-white text-[#171717] font-medium border border-[#e5e5e5]'
                          : 'text-[#737373] hover:text-[#171717] hover:bg-[#f5f5f5]'
                      }`}
                    >
                      <BookOpen size={14} />
                      {m.title}
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </li>

          <li className="pt-4">
            <Link
              href="/review"
              className={`flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors ${
                isActive('/review')
                  ? 'bg-white text-[#171717] font-medium border border-[#e5e5e5]'
                  : 'text-[#737373] hover:text-[#171717] hover:bg-[#f5f5f5]'
              }`}
            >
              <RotateCcw size={16} />
              Review
            </Link>
          </li>

          <li>
            <Link
              href="/dashboard/vocabulary"
              className={`flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors ${
                isActive('/dashboard/vocabulary')
                  ? 'bg-white text-[#171717] font-medium border border-[#e5e5e5]'
                  : 'text-[#737373] hover:text-[#171717] hover:bg-[#f5f5f5]'
              }`}
            >
              <Library size={16} />
              Kelimelerim
            </Link>
          </li>
        </ul>
      </nav>
    </aside>
  )
}
