'use client'

import { useEffect, useState } from 'react'
import { supabase } from '@/lib/supabase'
import Link from 'next/link'
import { BookOpen, RotateCcw, ListChecks, ArrowRight } from 'lucide-react'

interface Module {
  id: string
  slug: string
  title: string
  description: string | null
  status: string
  sort_order: number
}

interface Stats {
  dueCards: number
  pendingTasks: number
  topicsTotal: number
  topicsCompleted: number
}

export default function DashboardPage() {
  const [modules, setModules] = useState<Module[]>([])
  const [stats, setStats] = useState<Stats>({ dueCards: 0, pendingTasks: 0, topicsTotal: 0, topicsCompleted: 0 })
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function load() {
      const [{ data: mods }, { data: cards }, { data: tasks }, { data: topics }] = await Promise.all([
        supabase.from('lern_modules').select('*').order('sort_order'),
        supabase.from('lern_cards').select('id').lte('due_at', new Date().toISOString()).neq('state', 'new'),
        supabase.from('lern_tasks').select('id').eq('is_completed', false),
        supabase.from('lern_topics').select('id, status'),
      ])
      setModules(mods || [])
      setStats({
        dueCards: cards?.length || 0,
        pendingTasks: tasks?.length || 0,
        topicsTotal: topics?.length || 0,
        topicsCompleted: topics?.filter(t => t.status === 'completed').length || 0,
      })
      setLoading(false)
    }
    load()
  }, [])

  const activeModule = modules.find(m => m.status === 'active')

  if (loading) {
    return <div className="text-sm text-[#a3a3a3]">Loading...</div>
  }

  return (
    <div className="max-w-4xl">
      <h1 className="text-2xl font-bold tracking-tight text-[#171717] mb-6">Dashboard</h1>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
        <Link href="/review" className="bg-white border border-[#e5e5e5] rounded-lg p-4 hover:bg-[#fafafa] transition-colors">
          <div className="flex items-center gap-3 mb-2">
            <RotateCcw size={16} className="text-[#737373]" />
            <span className="text-xs font-medium text-[#a3a3a3] uppercase tracking-wide">Due Cards</span>
          </div>
          <p className="text-2xl font-bold text-[#171717]">{stats.dueCards}</p>
        </Link>

        <div className="bg-white border border-[#e5e5e5] rounded-lg p-4">
          <div className="flex items-center gap-3 mb-2">
            <ListChecks size={16} className="text-[#737373]" />
            <span className="text-xs font-medium text-[#a3a3a3] uppercase tracking-wide">Pending Tasks</span>
          </div>
          <p className="text-2xl font-bold text-[#171717]">{stats.pendingTasks}</p>
        </div>

        <div className="bg-white border border-[#e5e5e5] rounded-lg p-4">
          <div className="flex items-center gap-3 mb-2">
            <BookOpen size={16} className="text-[#737373]" />
            <span className="text-xs font-medium text-[#a3a3a3] uppercase tracking-wide">Topics</span>
          </div>
          <p className="text-2xl font-bold text-[#171717]">
            {stats.topicsCompleted}<span className="text-[#a3a3a3] text-lg font-normal">/{stats.topicsTotal}</span>
          </p>
        </div>
      </div>

      {activeModule && (
        <div className="mb-8">
          <h2 className="text-sm font-semibold text-[#171717] mb-3">Active Module</h2>
          <Link
            href={`/dashboard/${activeModule.slug}`}
            className="flex items-center justify-between bg-white border border-[#e5e5e5] rounded-lg p-5 hover:bg-[#fafafa] transition-colors"
          >
            <div>
              <p className="text-lg font-bold text-[#171717]">{activeModule.title}</p>
              {activeModule.description && (
                <p className="text-sm text-[#737373] mt-1">{activeModule.description}</p>
              )}
            </div>
            <ArrowRight size={16} className="text-[#a3a3a3]" />
          </Link>
        </div>
      )}

      <div>
        <h2 className="text-sm font-semibold text-[#171717] mb-3">All Modules</h2>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
          {modules.map(m => (
            <Link
              key={m.id}
              href={`/dashboard/${m.slug}`}
              className={`border rounded-lg p-4 transition-colors ${
                m.status === 'active'
                  ? 'border-[#171717] bg-white'
                  : m.status === 'completed'
                  ? 'border-[#e5e5e5] bg-[#fafafa]'
                  : 'border-[#e5e5e5] bg-white opacity-50'
              } hover:bg-[#f5f5f5]`}
            >
              <p className="font-bold text-[#171717]">{m.title}</p>
              <p className="text-xs text-[#a3a3a3] mt-1 capitalize">{m.status}</p>
            </Link>
          ))}
        </div>
      </div>
    </div>
  )
}
