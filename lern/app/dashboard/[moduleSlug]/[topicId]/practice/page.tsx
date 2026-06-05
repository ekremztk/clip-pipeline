'use client'

import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import { supabase } from '@/lib/supabase'
import Link from 'next/link'
import { ArrowLeft, Check, X, ChevronRight } from 'lucide-react'

interface Exercise {
  type: 'fill_blank' | 'translate' | 'transform' | 'choose'
  question: string
  answer: string
  hint?: string
  options?: string[]
}

function normalizeAnswer(s: string): string {
  return s
    .trim()
    .replace(/\.$/,  '')
    .replace(/ß/g, 'ss')
    .replace(/ä/g, 'a').replace(/Ä/g, 'A')
    .replace(/ö/g, 'o').replace(/Ö/g, 'O')
    .replace(/ü/g, 'u').replace(/Ü/g, 'U')
}

function checkAnswer(userInput: string, correctAnswer: string): boolean {
  const user = normalizeAnswer(userInput)
  const correct = normalizeAnswer(correctAnswer)
  if (user.toLowerCase() === correct.toLowerCase()) return true
  if (user === correct) return true
  const userNoCase = user.toLowerCase()
  const correctNoCase = correct.toLowerCase()
  if (userNoCase === correctNoCase) return true
  return false
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

  function doCheck() {
    const correct = checkAnswer(userAnswer, exercises[currentIndex].answer)
    setShowResult(correct ? 'correct' : 'wrong')
    setScore(s => ({ correct: s.correct + (correct ? 1 : 0), total: s.total + 1 }))
  }

  function next() {
    setShowResult(null)
    setUserAnswer('')
    setCurrentIndex(i => i + 1)
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter') {
      if (showResult) {
        next()
      } else if (userAnswer.trim()) {
        doCheck()
      }
    }
  }

  if (loading) return <div className="text-sm text-[#a3a3a3]">Laden...</div>

  const exercise = exercises[currentIndex]

  return (
    <div className="max-w-2xl">
      <Link
        href={`/dashboard/${moduleSlug}/${topicId}`}
        className="flex items-center gap-2 text-sm text-[#737373] hover:text-[#171717] mb-4 transition-colors"
      >
        <ArrowLeft size={14} />
        Zurück
      </Link>

      <h1 className="text-2xl font-bold tracking-tight text-[#171717] mb-6">Üben</h1>

      {exercises.length === 0 ? (
        <div className="border border-dashed border-[#e5e5e5] rounded-lg p-8 text-center">
          <p className="text-sm text-[#a3a3a3]">Noch keine Übungen</p>
        </div>
      ) : currentIndex >= exercises.length ? (
        <div className="border border-[#e5e5e5] rounded-lg p-8 text-center">
          <p className="text-lg font-bold text-[#171717]">Fertig!</p>
          <p className="text-sm text-[#737373] mt-2">
            Ergebnis: {score.correct}/{score.total} ({Math.round((score.correct / score.total) * 100)}%)
          </p>
          <div className="flex gap-3 justify-center mt-5">
            <button
              onClick={() => { setCurrentIndex(0); setScore({ correct: 0, total: 0 }) }}
              className="h-9 px-4 border border-[#e5e5e5] text-sm rounded-md hover:bg-[#f5f5f5] transition-colors"
            >
              Nochmal
            </button>
            <Link
              href={`/dashboard/${moduleSlug}/${topicId}/test`}
              className="inline-flex items-center gap-2 h-9 px-4 bg-[#171717] text-white text-sm rounded-md hover:bg-[#2a2a2a] transition-colors"
            >
              Weiter zum Test
              <ChevronRight size={14} />
            </Link>
          </div>
        </div>
      ) : (
        <div className="border border-[#e5e5e5] rounded-lg p-6">
          <div className="flex items-center justify-between mb-4">
            <span className="text-xs text-[#a3a3a3]">{currentIndex + 1} / {exercises.length}</span>
            <span className="text-xs text-[#a3a3a3] capitalize">{exercise.type.replace('_', ' ')}</span>
          </div>

          <p className="text-sm font-medium text-[#171717] mb-4">{exercise.question}</p>

          {exercise.hint && !showResult && (
            <p className="text-xs text-[#a3a3a3] mb-3">Hinweis: {exercise.hint}</p>
          )}

          {exercise.type === 'choose' && exercise.options ? (
            <div className="space-y-2">
              {exercise.options.map((opt, i) => (
                <button
                  key={i}
                  onClick={() => { setUserAnswer(opt); }}
                  disabled={!!showResult}
                  className={`w-full text-left px-4 py-2 border rounded-md text-sm transition-colors ${
                    showResult && opt === exercise.answer ? 'border-green-300 bg-green-50' :
                    showResult && userAnswer === opt && opt !== exercise.answer ? 'border-red-300 bg-red-50' :
                    'border-[#e5e5e5] hover:bg-[#f5f5f5]'
                  } disabled:cursor-default`}
                >
                  {opt}
                </button>
              ))}
            </div>
          ) : (
            <div className="flex gap-2" onKeyDown={handleKeyDown}>
              <input
                type="text"
                value={userAnswer}
                onChange={e => setUserAnswer(e.target.value)}
                placeholder="Deine Antwort..."
                disabled={!!showResult}
                autoFocus
                className="flex-1 h-10 px-3 text-sm border border-[#e5e5e5] rounded-md focus:outline-none focus:border-[#171717] disabled:opacity-50 transition-colors"
              />
              {!showResult && (
                <button
                  onClick={doCheck}
                  disabled={!userAnswer.trim()}
                  className="h-10 px-4 bg-[#171717] text-white text-sm rounded-md hover:bg-[#2a2a2a] disabled:opacity-30 transition-colors"
                >
                  Prüfen
                </button>
              )}
            </div>
          )}

          {showResult && (
            <div className={`mt-4 p-3 rounded-lg flex items-center gap-2 ${
              showResult === 'correct' ? 'bg-green-50 border border-green-200 text-green-700' : 'bg-red-50 border border-red-200 text-red-700'
            }`}>
              {showResult === 'correct' ? <Check size={16} /> : <X size={16} />}
              <span className="text-sm">
                {showResult === 'correct' ? 'Richtig!' : `Falsch. Antwort: ${exercise.answer}`}
              </span>
            </div>
          )}

          {showResult && (
            <button
              onClick={next}
              autoFocus
              className="mt-4 inline-flex items-center gap-2 h-9 px-4 border border-[#e5e5e5] text-sm rounded-md hover:bg-[#f5f5f5] transition-colors"
            >
              Weiter <ChevronRight size={14} />
            </button>
          )}
        </div>
      )}
    </div>
  )
}
