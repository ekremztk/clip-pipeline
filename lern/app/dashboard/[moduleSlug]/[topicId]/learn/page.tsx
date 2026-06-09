'use client'

import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import { supabase } from '@/lib/supabase'
import Link from 'next/link'
import { ArrowLeft, ChevronRight, Eye } from 'lucide-react'
import { useLang } from '@/lib/language-context'

interface ContentBlock {
  type: 'heading' | 'text' | 'example' | 'table' | 'tip' | 'rule' | 'conjugation' | 'translate'
  content: string
  translation?: string
  translation_ru?: string
  items?: string[]
  rows?: string[][]
  columns?: string[]
}

export default function LearnPage() {
  const params = useParams()
  const moduleSlug = params.moduleSlug as string
  const topicId = params.topicId as string
  const [content, setContent] = useState<ContentBlock[]>([])
  const [title, setTitle] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function load() {
      const { data } = await supabase
        .from('lern_pages')
        .select('title, content')
        .eq('topic_id', topicId)
        .eq('page_type', 'learn')
        .single()
      if (data) {
        setTitle(data.title)
        setContent(data.content?.blocks || [])
      }
      setLoading(false)
    }
    load()
  }, [topicId])

  if (loading) return <div className="text-sm text-[#a3a3a3]">Laden...</div>

  return (
    <div className="max-w-2xl">
      <Link
        href={`/dashboard/${moduleSlug}/${topicId}`}
        className="flex items-center gap-2 text-sm text-[#737373] hover:text-[#171717] mb-4 transition-colors"
      >
        <ArrowLeft size={14} />
        Zurück
      </Link>

      <h1 className="text-2xl font-bold tracking-tight text-[#171717] mb-8">{title || 'Lernen'}</h1>

      {content.length === 0 ? (
        <div className="border border-dashed border-[#e5e5e5] rounded-lg p-8 text-center">
          <p className="text-sm text-[#a3a3a3]">Noch kein Inhalt</p>
          <p className="text-xs text-[#a3a3a3] mt-1">Diese Seite wird nach deiner Kursstunde gefüllt</p>
        </div>
      ) : (
        <div className="space-y-5">
          {content.map((block, i) => (
            <ContentRenderer key={i} block={block} />
          ))}
        </div>
      )}

      <div className="mt-10 pt-6 border-t border-[#e5e5e5]">
        <Link
          href={`/dashboard/${moduleSlug}/${topicId}/practice`}
          className="inline-flex items-center gap-2 h-10 px-5 bg-[#171717] text-white text-sm font-medium rounded-md hover:bg-[#2a2a2a] transition-colors"
        >
          Weiter zum Üben
          <ChevronRight size={14} />
        </Link>
      </div>
    </div>
  )
}

function TranslateToggle({ translation }: { translation: string }) {
  const { lang } = useLang()
  const [show, setShow] = useState(true)
  const label = lang === 'ru' ? 'перевод' : 'çeviri'
  const hide  = lang === 'ru' ? 'скрыть'  : 'gizle'
  return (
    <span className="inline-flex items-center gap-1 ml-2">
      <button
        onClick={() => setShow(!show)}
        className="inline-flex items-center gap-1 text-xs text-[#a3a3a3] hover:text-[#737373] transition-colors"
      >
        <Eye size={11} />
        {show ? hide : label}
      </button>
      {show && <span className="text-xs text-[#a3a3a3] italic ml-1">({translation})</span>}
    </span>
  )
}

function useTranslation(block: ContentBlock): string | undefined {
  const { lang } = useLang()
  return lang === 'ru' ? (block.translation_ru || block.translation) : block.translation
}

function ContentRenderer({ block }: { block: ContentBlock }) {
  const translation = useTranslation(block)
  switch (block.type) {
    case 'heading':
      return <h2 className="text-lg font-semibold text-[#171717] mt-8 mb-2">{block.content}</h2>

    case 'text':
      return (
        <div>
          <p className="text-sm text-[#525252] leading-relaxed">{block.content}</p>
          {translation && <TranslateToggle translation={translation} />}
        </div>
      )

    case 'example':
      return (
        <div className="bg-[#f8faf8] border border-[#d4edda] rounded-lg p-5">
          <p className="text-sm font-medium text-[#171717] mb-2">{block.content}</p>
          {translation && <TranslateToggle translation={translation} />}
          {block.items && (
            <ul className="mt-3 space-y-2">
              {block.items.map((item, i) => (
                <li key={i} className="text-sm text-[#525252] pl-3 border-l-2 border-[#c3e6cb]">{item}</li>
              ))}
            </ul>
          )}
        </div>
      )

    case 'conjugation':
      if (!block.rows || !block.columns) return null
      return (
        <div className="rounded-lg overflow-hidden border border-[#e5e5e5]">
          <div className="grid gap-px bg-[#e5e5e5]" style={{ gridTemplateColumns: `repeat(${block.columns.length}, minmax(0, 1fr))` }}>
            {block.columns.map((col, j) => (
              <div key={j} className="bg-[#171717] text-white px-4 py-2.5 text-xs font-semibold uppercase tracking-wide">
                {col}
              </div>
            ))}
            {block.rows.map((row, i) =>
              row.map((cell, j) => (
                <div
                  key={`${i}-${j}`}
                  className={`px-4 py-2.5 text-sm ${
                    j === 0 ? 'bg-[#fafafa] font-medium text-[#171717]' : 'bg-white text-[#525252]'
                  }`}
                >
                  {cell}
                </div>
              ))
            )}
          </div>
        </div>
      )

    case 'table':
      if (!block.rows) return null
      const headers = block.rows[0]
      const body = block.rows.slice(1)
      return (
        <div className="rounded-lg overflow-hidden border border-[#e5e5e5]">
          <div className="grid gap-px bg-[#e5e5e5]" style={{ gridTemplateColumns: `repeat(${headers.length}, minmax(0, 1fr))` }}>
            {headers.map((h, j) => (
              <div key={j} className="bg-[#f5f5f5] px-4 py-2.5 text-xs font-semibold text-[#737373] uppercase tracking-wide">
                {h}
              </div>
            ))}
            {body.map((row, i) =>
              row.map((cell, j) => (
                <div key={`${i}-${j}`} className={`px-4 py-2.5 text-sm bg-white text-[#525252] ${i % 2 === 1 ? 'bg-[#fafafa]' : ''}`}>
                  {cell}
                </div>
              ))
            )}
          </div>
        </div>
      )

    case 'tip':
      return (
        <div className="bg-[#fffbf0] border border-[#fde68a] rounded-lg p-4 flex gap-3">
          <span className="text-base">💡</span>
          <div>
            <p className="text-sm text-[#525252]">{block.content}</p>
            {translation && <TranslateToggle translation={translation} />}
          </div>
        </div>
      )

    case 'rule':
      return (
        <div className="bg-[#f0f4ff] border border-[#bfdbfe] rounded-lg p-4 flex gap-3">
          <span className="text-base">📐</span>
          <div>
            <p className="text-sm font-medium text-[#171717]">{block.content}</p>
            {translation && <TranslateToggle translation={translation} />}
          </div>
        </div>
      )

    case 'translate':
      return <TranslateBlock content={block.content} translation={translation || ''} />

    default:
      return null
  }
}

function TranslateBlock({ content, translation }: { content: string; translation: string }) {
  const { lang } = useLang()
  const [show, setShow] = useState(true)
  const showLabel = lang === 'ru' ? 'Übersetzung anzeigen' : 'Übersetzung anzeigen'
  const hideLabel = lang === 'ru' ? 'Übersetzung ausblenden' : 'Übersetzung ausblenden'
  return (
    <div className="bg-[#fafafa] border border-[#e5e5e5] rounded-lg p-4">
      <p className="text-sm text-[#525252]">{content}</p>
      <button
        onClick={() => setShow(!show)}
        className="mt-2 flex items-center gap-1 text-xs text-[#a3a3a3] hover:text-[#737373] transition-colors"
      >
        <Eye size={11} />
        {show ? hideLabel : showLabel}
      </button>
      {show && <p className="mt-2 text-xs text-[#a3a3a3] italic border-t border-[#e5e5e5] pt-2">{translation}</p>}
    </div>
  )
}
