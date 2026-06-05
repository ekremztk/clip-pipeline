'use client'

import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import { supabase } from '@/lib/supabase'
import Link from 'next/link'
import { ArrowLeft, Circle, CheckCircle2, Loader2 } from 'lucide-react'

interface Topic {
  id: string
  title: string
  description: string | null
  status: string
  sort_order: number
}

interface Module {
  id: string
  slug: string
  title: string
  description: string | null
  status: string
}

export default function ModulePage() {
  const params = useParams()
  const moduleSlug = params.moduleSlug as string
  const [module_, setModule] = useState<Module | null>(null)
  const [topics, setTopics] = useState<Topic[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function load() {
      const { data: mod } = await supabase
        .from('lern_modules')
        .select('*')
        .eq('slug', moduleSlug)
        .single()

      if (mod) {
        setModule(mod)
        const { data: t } = await supabase
          .from('lern_topics')
          .select('*')
          .eq('module_id', mod.id)
          .order('sort_order')
        setTopics(t || [])
      }
      setLoading(false)
    }
    load()
  }, [moduleSlug])

  if (loading) {
    return <div className="text-sm text-[#a3a3a3]">Laden...</div>
  }

  if (!module_) {
    return <div className="text-sm text-[#737373]">Modul nicht gefunden</div>
  }

  const completedCount = topics.filter(t => t.status === 'completed').length
  const progressPercent = topics.length > 0 ? (completedCount / topics.length) * 100 : 0

  return (
    <div className="max-w-3xl">
      <Link href="/dashboard" className="flex items-center gap-2 text-sm text-[#737373] hover:text-[#171717] mb-4 transition-colors">
        <ArrowLeft size={14} />
        Zurück
      </Link>

      <div className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight text-[#171717]">{module_.title}</h1>
        {module_.description && (
          <p className="text-sm text-[#737373] mt-1">{module_.description}</p>
        )}
      </div>

      {topics.length > 0 && (
        <div className="mb-6">
          <div className="flex items-center justify-between text-xs text-[#a3a3a3] mb-2">
            <span>{completedCount} von {topics.length} Themen abgeschlossen</span>
            <span>{Math.round(progressPercent)}%</span>
          </div>
          <div className="h-2 bg-[#f5f5f5] rounded-full overflow-hidden border border-[#e5e5e5]">
            <div
              className="h-full bg-[#171717] rounded-full transition-all duration-300"
              style={{ width: `${progressPercent}%` }}
            />
          </div>
        </div>
      )}

      {topics.length === 0 ? (
        <div className="border border-dashed border-[#e5e5e5] rounded-lg p-8 text-center">
          <p className="text-sm text-[#a3a3a3]">Noch keine Themen</p>
          <p className="text-xs text-[#a3a3a3] mt-1">Themen werden mit dem Kursfortschritt hinzugefügt</p>
        </div>
      ) : (
        <div className="space-y-2">
          {topics.map((topic, i) => (
            <Link
              key={topic.id}
              href={`/dashboard/${moduleSlug}/${topic.id}`}
              className="flex items-center gap-4 p-4 border border-[#e5e5e5] rounded-lg hover:bg-[#fafafa] transition-colors"
            >
              <span className="text-xs text-[#a3a3a3] w-6">{i + 1}</span>
              {topic.status === 'completed' ? (
                <CheckCircle2 size={18} className="text-[#171717]" />
              ) : topic.status === 'in_progress' ? (
                <Loader2 size={18} className="text-[#737373]" />
              ) : (
                <Circle size={18} className="text-[#e5e5e5]" />
              )}
              <div className="flex-1">
                <p className="text-sm font-medium text-[#171717]">{topic.title}</p>
                {topic.description && (
                  <p className="text-xs text-[#a3a3a3] mt-0.5">{topic.description}</p>
                )}
              </div>
              <span className={`text-xs px-2 py-0.5 rounded-full ${
                topic.status === 'completed' ? 'bg-[#f5f5f5] text-[#171717]' :
                topic.status === 'in_progress' ? 'bg-[#f5f5f5] text-[#737373]' :
                'text-[#a3a3a3]'
              }`}>
                {topic.status === 'completed' ? 'Fertig' : topic.status === 'in_progress' ? 'In Bearbeitung' : ''}
              </span>
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
