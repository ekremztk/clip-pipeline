'use client'

import { useEffect, useState, useMemo } from 'react'
import { useParams } from 'next/navigation'
import { supabase } from '@/lib/supabase'
import Link from 'next/link'
import { ArrowLeft, Check, X, ChevronRight, RotateCcw } from 'lucide-react'

interface Card {
  id: string
  front: string
  back: string
  example_sentence: string | null
}

function shuffle<T>(arr: T[]): T[] {
  const a = [...arr]
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[a[i], a[j]] = [a[j], a[i]]
  }
  return a
}

function generateOptions(cards: Card[], currentIndex: number): string[] {
  const correct = cards[currentIndex].back
  const others = cards
    .filter((_, i) => i !== currentIndex)
    .map(c => c.back)
  const distractors = shuffle(others).slice(0, 3)
  return shuffle([correct, ...distractors])
}

export default function CardsPage() {
  const params = useParams()
  const moduleSlug = params.moduleSlug as string
  const topicId = params.topicId as string
  const [cards, setCards] = useState<Card[]>([])
  const [currentIndex, setCurrentIndex] = useState(0)
  const [selected, setSelected] = useState<string | null>(null)
  const [score, setScore] = useState({ correct: 0, total: 0 })
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function load() {
      const { data } = await supabase
        .from('lern_cards')
        .select('id, front, back, example_sentence')
        .eq('topic_id', topicId)
        .order('created_at')
      setCards(shuffle(data || []))
      setLoading(false)
    }
    load()
  }, [topicId])

  const options = useMemo(() => {
    if (cards.length < 2 || currentIndex >= cards.length) return []
    return generateOptions(cards, currentIndex)
  }, [cards, currentIndex])

  function handleSelect(option: string) {
    if (selected) return
    setSelected(option)
    const isCorrect = option === cards[currentIndex].back
    setScore(s => ({ correct: s.correct + (isCorrect ? 1 : 0), total: s.total + 1 }))
  }

  function next() {
    setSelected(null)
    setCurrentIndex(i => i + 1)
  }

  function restart() {
    setCards(shuffle([...cards]))
    setCurrentIndex(0)
    setSelected(null)
    setScore({ correct: 0, total: 0 })
  }

  if (loading) return <div className="text-sm text-[#a3a3a3]">Laden...</div>

  const card = cards[currentIndex]

  return (
    <div className="max-w-2xl">
      <Link
        href={`/dashboard/${moduleSlug}/${topicId}`}
        className="flex items-center gap-2 text-sm text-[#737373] hover:text-[#171717] mb-4 transition-colors"
      >
        <ArrowLeft size={14} />
        Zurück
      </Link>

      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold tracking-tight text-[#171717]">Kartlar</h1>
        {cards.length > 0 && currentIndex < cards.length && (
          <span className="text-xs text-[#a3a3a3]">{currentIndex + 1} / {cards.length}</span>
        )}
      </div>

      {cards.length === 0 ? (
        <div className="border border-dashed border-[#e5e5e5] rounded-lg p-8 text-center">
          <p className="text-sm text-[#a3a3a3]">Noch keine Karten</p>
        </div>
      ) : cards.length < 4 ? (
        <div className="border border-dashed border-[#e5e5e5] rounded-lg p-8 text-center">
          <p className="text-sm text-[#a3a3a3]">Mindestens 4 Karten nötig</p>
        </div>
      ) : currentIndex >= cards.length ? (
        <div className="border border-[#e5e5e5] rounded-lg p-8 text-center">
          <p className="text-3xl font-bold text-[#171717]">{score.correct}/{score.total}</p>
          <p className="text-sm text-[#737373] mt-2">
            {score.correct === score.total ? 'Perfekt!' :
             score.correct >= score.total * 0.8 ? 'Sehr gut!' :
             score.correct >= score.total * 0.6 ? 'Gut, übe weiter!' : 'Du musst mehr üben!'}
          </p>
          <div className="flex gap-3 justify-center mt-5">
            <button
              onClick={restart}
              className="inline-flex items-center gap-2 h-9 px-4 border border-[#e5e5e5] text-sm rounded-md hover:bg-[#f5f5f5] transition-colors"
            >
              <RotateCcw size={14} />
              Nochmal
            </button>
            <Link
              href={`/dashboard/${moduleSlug}/${topicId}/vocabulary`}
              className="inline-flex items-center gap-2 h-9 px-4 bg-[#171717] text-white text-sm rounded-md hover:bg-[#2a2a2a] transition-colors"
            >
              Weiter zu Wörtern
              <ChevronRight size={14} />
            </Link>
          </div>
        </div>
      ) : (
        <div className="border border-[#e5e5e5] rounded-lg p-6">
          <p className="text-base font-medium text-[#171717] mb-5">{card.front}</p>

          <div className="space-y-2">
            {options.map((opt, i) => {
              let style = 'border-[#e5e5e5] hover:bg-[#f5f5f5]'
              if (selected) {
                if (opt === card.back) {
                  style = 'border-green-300 bg-green-50'
                } else if (opt === selected && opt !== card.back) {
                  style = 'border-red-300 bg-red-50'
                } else {
                  style = 'border-[#e5e5e5] opacity-50'
                }
              }
              return (
                <button
                  key={i}
                  onClick={() => handleSelect(opt)}
                  disabled={!!selected}
                  className={`w-full text-left px-4 py-3 border rounded-lg text-sm transition-colors disabled:cursor-default ${style}`}
                >
                  <span className="text-[#a3a3a3] mr-2">{String.fromCharCode(65 + i)}.</span>
                  {opt}
                </button>
              )
            })}
          </div>

          {selected && (
            <div className={`mt-4 p-3 rounded-lg flex items-center gap-2 ${
              selected === card.back
                ? 'bg-green-50 border border-green-200 text-green-700'
                : 'bg-red-50 border border-red-200 text-red-700'
            }`}>
              {selected === card.back ? <Check size={16} /> : <X size={16} />}
              <span className="text-sm">
                {selected === card.back ? 'Richtig!' : `Falsch. Antwort: ${card.back}`}
              </span>
            </div>
          )}

          {selected && card.example_sentence && (
            <p className="mt-3 text-xs text-[#737373] italic border-t border-[#e5e5e5] pt-3">
              {card.example_sentence}
            </p>
          )}

          {selected && (
            <button
              onClick={next}
              autoFocus
              className="mt-4 inline-flex items-center gap-2 h-9 px-4 bg-[#171717] text-white text-sm rounded-md hover:bg-[#2a2a2a] transition-colors"
            >
              Weiter <ChevronRight size={14} />
            </button>
          )}
        </div>
      )}
    </div>
  )
}
