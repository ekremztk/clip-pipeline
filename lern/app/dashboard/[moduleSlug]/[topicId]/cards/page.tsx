'use client'

import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import { supabase } from '@/lib/supabase'
import Link from 'next/link'
import { ArrowLeft, RotateCcw } from 'lucide-react'

interface Card {
  id: string
  front: string
  back: string
  example_sentence: string | null
  state: string
}

export default function CardsPage() {
  const params = useParams()
  const moduleSlug = params.moduleSlug as string
  const topicId = params.topicId as string
  const [cards, setCards] = useState<Card[]>([])
  const [currentIndex, setCurrentIndex] = useState(0)
  const [flipped, setFlipped] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function load() {
      const { data } = await supabase
        .from('lern_cards')
        .select('id, front, back, example_sentence, state')
        .eq('topic_id', topicId)
        .order('created_at')
      setCards(data || [])
      setLoading(false)
    }
    load()
  }, [topicId])

  function handleRate(rating: 'again' | 'hard' | 'good' | 'easy') {
    setFlipped(false)
    setCurrentIndex(i => i + 1)
  }

  if (loading) return <div className="text-sm text-[#a3a3a3]">Loading...</div>

  const card = cards[currentIndex]

  return (
    <div className="max-w-2xl">
      <Link
        href={`/dashboard/${moduleSlug}/${topicId}`}
        className="flex items-center gap-2 text-sm text-[#737373] hover:text-[#171717] mb-4 transition-colors"
      >
        <ArrowLeft size={14} />
        Back to topic
      </Link>

      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold tracking-tight text-[#171717]">Kartlar</h1>
        {cards.length > 0 && (
          <span className="text-xs text-[#a3a3a3]">{currentIndex + 1} / {cards.length}</span>
        )}
      </div>

      {cards.length === 0 ? (
        <div className="border border-dashed border-[#e5e5e5] rounded-lg p-8 text-center">
          <p className="text-sm text-[#a3a3a3]">No cards yet</p>
          <p className="text-xs text-[#a3a3a3] mt-1">Flashcards will be generated from your course material</p>
        </div>
      ) : currentIndex >= cards.length ? (
        <div className="border border-[#e5e5e5] rounded-lg p-8 text-center">
          <RotateCcw size={24} className="mx-auto text-[#a3a3a3] mb-3" />
          <p className="text-lg font-bold text-[#171717]">Session complete</p>
          <p className="text-sm text-[#737373] mt-1">{cards.length} cards reviewed</p>
          <button
            onClick={() => { setCurrentIndex(0); setFlipped(false) }}
            className="mt-4 h-9 px-4 bg-[#171717] text-white text-sm rounded-md hover:bg-[#2a2a2a] transition-colors"
          >
            Start over
          </button>
        </div>
      ) : (
        <div>
          <div
            onClick={() => setFlipped(!flipped)}
            className="border border-[#e5e5e5] rounded-lg p-8 min-h-[200px] flex flex-col items-center justify-center cursor-pointer hover:bg-[#fafafa] transition-colors select-none"
          >
            {!flipped ? (
              <div className="text-center">
                <p className="text-lg font-medium text-[#171717]">{card.front}</p>
                <p className="text-xs text-[#a3a3a3] mt-4">Click to reveal</p>
              </div>
            ) : (
              <div className="text-center">
                <p className="text-lg font-bold text-[#171717]">{card.back}</p>
                {card.example_sentence && (
                  <p className="text-sm text-[#737373] mt-3 italic">{card.example_sentence}</p>
                )}
              </div>
            )}
          </div>

          {flipped && (
            <div className="grid grid-cols-4 gap-2 mt-4">
              <button
                onClick={() => handleRate('again')}
                className="h-10 text-sm border border-red-200 text-red-600 rounded-md hover:bg-red-50 transition-colors"
              >
                Again
              </button>
              <button
                onClick={() => handleRate('hard')}
                className="h-10 text-sm border border-orange-200 text-orange-600 rounded-md hover:bg-orange-50 transition-colors"
              >
                Hard
              </button>
              <button
                onClick={() => handleRate('good')}
                className="h-10 text-sm border border-green-200 text-green-600 rounded-md hover:bg-green-50 transition-colors"
              >
                Good
              </button>
              <button
                onClick={() => handleRate('easy')}
                className="h-10 text-sm border border-blue-200 text-blue-600 rounded-md hover:bg-blue-50 transition-colors"
              >
                Easy
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
