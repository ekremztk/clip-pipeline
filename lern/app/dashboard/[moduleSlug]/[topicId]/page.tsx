'use client'

import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import { supabase } from '@/lib/supabase'
import Link from 'next/link'
import {
  ArrowLeft,
  GraduationCap,
  PenLine,
  ClipboardCheck,
  Layers,
  BookA,
  ListTodo
} from 'lucide-react'

interface Topic {
  id: string
  title: string
  description: string | null
  module_id: string
}

interface PageInfo {
  page_type: string
  progress: number
  completed_at: string | null
}

const PAGE_TYPES = [
  { type: 'learn', label: 'Lernen', description: 'Thema verstehen', icon: GraduationCap, color: '#171717' },
  { type: 'practice', label: 'Üben', description: 'Aktiv üben', icon: PenLine, color: '#171717' },
  { type: 'test', label: 'Test', description: 'Dich selbst prüfen', icon: ClipboardCheck, color: '#171717' },
  { type: 'cards', label: 'Karten', description: 'Wiederholungskarten', icon: Layers, color: '#171717' },
  { type: 'vocabulary', label: 'Wörter', description: 'Wortschatz', icon: BookA, color: '#171717' },
  { type: 'tasks', label: 'Aufgaben', description: 'Tägliche Aufgaben', icon: ListTodo, color: '#171717' },
]

export default function TopicPage() {
  const params = useParams()
  const moduleSlug = params.moduleSlug as string
  const topicId = params.topicId as string
  const [topic, setTopic] = useState<Topic | null>(null)
  const [pages, setPages] = useState<PageInfo[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function load() {
      const [{ data: t }, { data: p }] = await Promise.all([
        supabase.from('lern_topics').select('*').eq('id', topicId).single(),
        supabase.from('lern_pages').select('page_type, progress, completed_at').eq('topic_id', topicId),
      ])
      setTopic(t)
      setPages(p || [])
      setLoading(false)
    }
    load()
  }, [topicId])

  if (loading) return <div className="text-sm text-[#a3a3a3]">Laden...</div>
  if (!topic) return <div className="text-sm text-[#737373]">Thema nicht gefunden</div>

  function getPageProgress(type: string): { progress: number; completed: boolean } {
    const page = pages.find(p => p.page_type === type)
    if (!page) return { progress: 0, completed: false }
    return { progress: page.progress, completed: !!page.completed_at }
  }

  return (
    <div className="max-w-3xl">
      <Link
        href={`/dashboard/${moduleSlug}`}
        className="flex items-center gap-2 text-sm text-[#737373] hover:text-[#171717] mb-4 transition-colors"
      >
        <ArrowLeft size={14} />
        Zurück
      </Link>

      <div className="mb-8">
        <h1 className="text-2xl font-bold tracking-tight text-[#171717]">{topic.title}</h1>
        {topic.description && (
          <p className="text-sm text-[#737373] mt-1">{topic.description}</p>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {PAGE_TYPES.map(({ type, label, description, icon: Icon }) => {
          const { progress, completed } = getPageProgress(type)
          return (
            <Link
              key={type}
              href={`/dashboard/${moduleSlug}/${topicId}/${type === 'learn' ? 'learn' : type === 'practice' ? 'practice' : type === 'test' ? 'test' : type === 'cards' ? 'cards' : type === 'vocabulary' ? 'vocabulary' : 'tasks'}`}
              className="border border-[#e5e5e5] rounded-lg p-5 hover:bg-[#fafafa] transition-colors group"
            >
              <div className="flex items-start justify-between mb-3">
                <div className="w-9 h-9 rounded-md bg-[#f5f5f5] flex items-center justify-center">
                  <Icon size={18} className="text-[#171717]" />
                </div>
                {completed && (
                  <span className="text-xs bg-[#171717] text-white px-2 py-0.5 rounded-full">Fertig</span>
                )}
              </div>
              <p className="font-medium text-[#171717] text-sm">{label}</p>
              <p className="text-xs text-[#a3a3a3] mt-1">{description}</p>
              {progress > 0 && !completed && (
                <div className="mt-3 h-1.5 bg-[#f5f5f5] rounded-full overflow-hidden">
                  <div
                    className="h-full bg-[#171717] rounded-full"
                    style={{ width: `${progress * 100}%` }}
                  />
                </div>
              )}
            </Link>
          )
        })}
      </div>
    </div>
  )
}
