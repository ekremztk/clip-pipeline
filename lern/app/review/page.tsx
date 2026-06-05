'use client'

import { useEffect, useState } from 'react'
import { supabase } from '@/lib/supabase'
import { RotateCcw } from 'lucide-react'
import { Sidebar } from '@/components/sidebar'
import { Header } from '@/components/header'

interface Card {
  id: string
  front: string
  back: string
  example_sentence: string | null
}

export default function ReviewPage() {
  const [cards, setCards] = useState<Card[]>([])
  const [currentIndex, setCurrentIndex] = useState(0)
  const [flipped, setFlipped] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function load() {
      const { data } = await supabase
        .from('lern_cards')
        .select('id, front, back, example_sentence')
        .lte('due_at', new Date().toISOString())
        .neq('state', 'new')
        .order('due_at')
      setCards(data || [])
      setLoading(false)
    }
    load()
  }, [])

  function handleRate() {
    setFlipped(false)
    setCurrentIndex(i => i + 1)
  }

  const card = cards[currentIndex]

  return (
    <div className="min-h-screen bg-white">
      <Sidebar />
      <div className="ml-[260px]">
        <Header />
        <main className="p-6 max-w-2xl">
          <h1 className="text-2xl font-bold tracking-tight text-[#171717] mb-6">Review</h1>

          {loading ? (
            <div className="text-sm text-[#a3a3a3]">Loading...</div>
          ) : cards.length === 0 ? (
            <div className="border border-dashed border-[#e5e5e5] rounded-lg p-8 text-center">
              <RotateCcw size={24} className="mx-auto text-[#a3a3a3] mb-3" />
              <p className="text-sm text-[#a3a3a3]">No cards due for review</p>
              <p className="text-xs text-[#a3a3a3] mt-1">Come back later or add new cards from your topics</p>
            </div>
          ) : currentIndex >= cards.length ? (
            <div className="border border-[#e5e5e5] rounded-lg p-8 text-center">
              <p className="text-lg font-bold text-[#171717]">All caught up!</p>
              <p className="text-sm text-[#737373] mt-2">{cards.length} cards reviewed</p>
            </div>
          ) : (
            <div>
              <div className="flex items-center justify-between mb-4">
                <span className="text-xs text-[#a3a3a3]">{currentIndex + 1} / {cards.length} due</span>
              </div>
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
                  <button onClick={handleRate} className="h-10 text-sm border border-red-200 text-red-600 rounded-md hover:bg-red-50">Again</button>
                  <button onClick={handleRate} className="h-10 text-sm border border-orange-200 text-orange-600 rounded-md hover:bg-orange-50">Hard</button>
                  <button onClick={handleRate} className="h-10 text-sm border border-green-200 text-green-600 rounded-md hover:bg-green-50">Good</button>
                  <button onClick={handleRate} className="h-10 text-sm border border-blue-200 text-blue-600 rounded-md hover:bg-blue-50">Easy</button>
                </div>
              )}
            </div>
          )}
        </main>
      </div>
    </div>
  )
}
