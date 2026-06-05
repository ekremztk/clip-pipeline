'use client'

import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import { supabase } from '@/lib/supabase'
import Link from 'next/link'
import { ArrowLeft, Check, X } from 'lucide-react'

interface Exercise {
  type: 'fill_blank' | 'translate' | 'transform' | 'choose'
  question: string
  answer: string
  hint?: string
  options?: string[]
}

export default function PracticePage() {
  const params = useParams()
  const moduleSlug = params.moduleSlug as string
  const topicId = params.topicId as string
  const [exercises, setExercises] = useState<Exercise[]>([])
  const [currentIndex, setCurrentIndex] = useState(0)
  const [userAnswer, setUserAnswer] = useState('')
  const [showResult, setShowResult] = useState<'correct' | 'wrong' | null>(null)
  const [score, setScore] = useState({ correct: 0, total: 0 })
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function load() {
      const { data } = await supabase
        .from('lern_pages')
        .select('content')
        .eq('topic_id', topicId)
        .eq('page_type', 'practice')
        .single()
      if (data?.content?.exercises) {
        setExercises(data.content.exercises)
      }
      setLoading(false)
    }
    load()
  }, [topicId])

  function checkAnswer() {
    const correct = userAnswer.trim().toLowerCase() === exercises[currentIndex].answer.toLowerCase()
    setShowResult(correct ? 'correct' : 'wrong')
    setScore(s => ({ correct: s.correct + (correct ? 1 : 0), total: s.total + 1 }))
  }

  function next() {
    setShowResult(null)
    setUserAnswer('')
    setCurrentIndex(i => i + 1)
  }

  if (loading) return <div className="text-sm text-[#a3a3a3]">Loading...</div>

  const exercise = exercises[currentIndex]

  return (
    <div className="max-w-2xl">
      <Link
        href={`/dashboard/${moduleSlug}/${topicId}`}
        className="flex items-center gap-2 text-sm text-[#737373] hover:text-[#171717] mb-4 transition-colors"
      >
        <ArrowLeft size={14} />
        Back to topic
      </Link>

      <h1 className="text-2xl font-bold tracking-tight text-[#171717] mb-6">Çalış</h1>

      {exercises.length === 0 ? (
        <div className="border border-dashed border-[#e5e5e5] rounded-lg p-8 text-center">
          <p className="text-sm text-[#a3a3a3]">No exercises yet</p>
          <p className="text-xs text-[#a3a3a3] mt-1">Exercises will be added after your course session</p>
        </div>
      ) : currentIndex >= exercises.length ? (
        <div className="border border-[#e5e5e5] rounded-lg p-8 text-center">
          <p className="text-lg font-bold text-[#171717]">Complete!</p>
          <p className="text-sm text-[#737373] mt-2">
            Score: {score.correct}/{score.total} ({Math.round((score.correct / score.total) * 100)}%)
          </p>
          <button
            onClick={() => { setCurrentIndex(0); setScore({ correct: 0, total: 0 }) }}
            className="mt-4 h-9 px-4 bg-[#171717] text-white text-sm rounded-md hover:bg-[#2a2a2a] transition-colors"
          >
            Try again
          </button>
        </div>
      ) : (
        <div className="border border-[#e5e5e5] rounded-lg p-6">
          <div className="flex items-center justify-between mb-4">
            <span className="text-xs text-[#a3a3a3]">{currentIndex + 1} / {exercises.length}</span>
            <span className="text-xs text-[#a3a3a3] capitalize">{exercise.type.replace('_', ' ')}</span>
          </div>

          <p className="text-sm font-medium text-[#171717] mb-4">{exercise.question}</p>

          {exercise.hint && (
            <p className="text-xs text-[#a3a3a3] mb-3">Hint: {exercise.hint}</p>
          )}

          {exercise.type === 'choose' && exercise.options ? (
            <div className="space-y-2">
              {exercise.options.map((opt, i) => (
                <button
                  key={i}
                  onClick={() => { setUserAnswer(opt); setTimeout(checkAnswer, 100) }}
                  disabled={!!showResult}
                  className="w-full text-left px-4 py-2 border border-[#e5e5e5] rounded-md text-sm hover:bg-[#f5f5f5] transition-colors disabled:opacity-50"
                >
                  {opt}
                </button>
              ))}
            </div>
          ) : (
            <div className="flex gap-2">
              <input
                type="text"
                value={userAnswer}
                onChange={e => setUserAnswer(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && !showResult && checkAnswer()}
                placeholder="Your answer..."
                disabled={!!showResult}
                className="flex-1 h-9 px-3 text-sm border border-[#e5e5e5] rounded-md focus:outline-none focus:border-[#171717] disabled:opacity-50"
              />
              {!showResult && (
                <button
                  onClick={checkAnswer}
                  className="h-9 px-4 bg-[#171717] text-white text-sm rounded-md hover:bg-[#2a2a2a] transition-colors"
                >
                  Check
                </button>
              )}
            </div>
          )}

          {showResult && (
            <div className={`mt-4 p-3 rounded-md flex items-center gap-2 ${
              showResult === 'correct' ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'
            }`}>
              {showResult === 'correct' ? <Check size={16} /> : <X size={16} />}
              <span className="text-sm">
                {showResult === 'correct' ? 'Correct!' : `Wrong. Answer: ${exercise.answer}`}
              </span>
            </div>
          )}

          {showResult && (
            <button
              onClick={next}
              className="mt-4 h-9 px-4 border border-[#e5e5e5] text-sm rounded-md hover:bg-[#f5f5f5] transition-colors"
            >
              Next →
            </button>
          )}
        </div>
      )}
    </div>
  )
}
