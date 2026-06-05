'use client'

import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import { supabase } from '@/lib/supabase'
import Link from 'next/link'
import { ArrowLeft } from 'lucide-react'

interface VocabItem {
  id: string
  word: string
  article: string | null
  plural: string | null
  translation: string
  example_sentence: string | null
  word_type: string | null
  mastery: number
}

export default function VocabularyPage() {
  const params = useParams()
  const moduleSlug = params.moduleSlug as string
  const topicId = params.topicId as string
  const [vocab, setVocab] = useState<VocabItem[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function load() {
      const { data } = await supabase
        .from('lern_vocabulary')
        .select('*')
        .eq('topic_id', topicId)
        .order('created_at')
      setVocab(data || [])
      setLoading(false)
    }
    load()
  }, [topicId])

  if (loading) return <div className="text-sm text-[#a3a3a3]">Loading...</div>

  return (
    <div className="max-w-2xl">
      <Link
        href={`/dashboard/${moduleSlug}/${topicId}`}
        className="flex items-center gap-2 text-sm text-[#737373] hover:text-[#171717] mb-4 transition-colors"
      >
        <ArrowLeft size={14} />
        Back to topic
      </Link>

      <h1 className="text-2xl font-bold tracking-tight text-[#171717] mb-6">Kelimeler</h1>

      {vocab.length === 0 ? (
        <div className="border border-dashed border-[#e5e5e5] rounded-lg p-8 text-center">
          <p className="text-sm text-[#a3a3a3]">No vocabulary yet</p>
          <p className="text-xs text-[#a3a3a3] mt-1">Words will be added as you learn new topics</p>
        </div>
      ) : (
        <div className="border border-[#e5e5e5] rounded-lg overflow-hidden">
          <div className="grid grid-cols-[auto_1fr_1fr_auto] gap-px bg-[#f5f5f5] px-4 py-2 text-xs font-medium text-[#737373] uppercase tracking-wide">
            <span>Type</span>
            <span>Word</span>
            <span>Translation</span>
            <span>Mastery</span>
          </div>
          {vocab.map(v => (
            <div key={v.id} className="grid grid-cols-[auto_1fr_1fr_auto] gap-px px-4 py-3 border-t border-[#e5e5e5] items-center">
              <span className="text-xs text-[#a3a3a3] w-16 capitalize">{v.word_type || ''}</span>
              <div>
                <span className="text-sm font-medium text-[#171717]">
                  {v.article && <span className="text-[#a3a3a3] mr-1">{v.article}</span>}
                  {v.word}
                </span>
                {v.plural && <span className="text-xs text-[#a3a3a3] ml-2">(Pl. {v.plural})</span>}
              </div>
              <span className="text-sm text-[#737373]">{v.translation}</span>
              <div className="w-12 h-1.5 bg-[#f5f5f5] rounded-full overflow-hidden">
                <div className="h-full bg-[#171717] rounded-full" style={{ width: `${v.mastery * 100}%` }} />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
