'use client'

import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import { supabase } from '@/lib/supabase'
import Link from 'next/link'
import { ArrowLeft } from 'lucide-react'

interface ContentBlock {
  type: 'heading' | 'text' | 'example' | 'table' | 'tip' | 'rule'
  content: string
  items?: string[]
  rows?: string[][]
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

      <h1 className="text-2xl font-bold tracking-tight text-[#171717] mb-6">{title || 'Öğren'}</h1>

      {content.length === 0 ? (
        <div className="border border-dashed border-[#e5e5e5] rounded-lg p-8 text-center">
          <p className="text-sm text-[#a3a3a3]">Content not yet added</p>
          <p className="text-xs text-[#a3a3a3] mt-1">This page will be filled after your course session</p>
        </div>
      ) : (
        <div className="space-y-4">
          {content.map((block, i) => (
            <ContentRenderer key={i} block={block} />
          ))}
        </div>
      )}
    </div>
  )
}

function ContentRenderer({ block }: { block: ContentBlock }) {
  switch (block.type) {
    case 'heading':
      return <h2 className="text-lg font-semibold text-[#171717] mt-6">{block.content}</h2>
    case 'text':
      return <p className="text-sm text-[#737373] leading-relaxed">{block.content}</p>
    case 'example':
      return (
        <div className="bg-[#fafafa] border border-[#e5e5e5] rounded-md p-4">
          <p className="text-sm font-medium text-[#171717]">{block.content}</p>
          {block.items && (
            <ul className="mt-2 space-y-1">
              {block.items.map((item, i) => (
                <li key={i} className="text-sm text-[#737373]">• {item}</li>
              ))}
            </ul>
          )}
        </div>
      )
    case 'table':
      return (
        <div className="border border-[#e5e5e5] rounded-md overflow-hidden">
          {block.rows?.map((row, i) => (
            <div
              key={i}
              className={`grid grid-cols-${row.length} gap-px ${i === 0 ? 'bg-[#f5f5f5] font-medium' : 'bg-white'}`}
            >
              {row.map((cell, j) => (
                <div key={j} className="px-3 py-2 text-sm text-[#171717] border-b border-[#e5e5e5]">{cell}</div>
              ))}
            </div>
          ))}
        </div>
      )
    case 'tip':
      return (
        <div className="bg-[#f5f5f5] border-l-2 border-[#171717] rounded-r-md p-4">
          <p className="text-sm text-[#171717]">{block.content}</p>
        </div>
      )
    case 'rule':
      return (
        <div className="bg-white border border-[#171717] rounded-md p-4">
          <p className="text-sm font-medium text-[#171717]">{block.content}</p>
        </div>
      )
    default:
      return null
  }
}
