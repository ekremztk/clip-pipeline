'use client'

import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import { supabase } from '@/lib/supabase'
import Link from 'next/link'
import { ArrowLeft, ChevronRight } from 'lucide-react'

interface TestQuestion {
  question: string
  answer: string
  type: 'fill_blank' | 'translate' | 'choose'
  options?: string[]
  points: number
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

function isCorrectAnswer(userInput: string, correctAnswer: string): boolean {
  const user = normalizeAnswer(userInput)
  const correct = normalizeAnswer(correctAnswer)
  return user.toLowerCase() === correct.toLowerCase()
}

export default function TestPage() {
  const params = useParams()
  const moduleSlug = params.moduleSlug as string
  const topicId = params.topicId as string
  const [questions, setQuestions] = useState<TestQuestion[]>([])
  const [answers, setAnswers] = useState<Record<number, string>>({})
  const [submitted, setSubmitted] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function load() {
      const { data } = await supabase
        .from('lern_pages')
        .select('content')
        .eq('topic_id', topicId)
        .eq('page_type', 'test')
        .single()
      if (data?.content?.questions) {
        setQuestions(data.content.questions)
      }
      setLoading(false)
    }
    load()
  }, [topicId])

  function handleSubmit() {
    setSubmitted(true)
  }

  function getScore() {
    let correct = 0
    questions.forEach((q, i) => {
      if (isCorrectAnswer(answers[i] || '', q.answer)) correct++
    })
    return correct
  }

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

      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold tracking-tight text-[#171717]">Test</h1>
        {!submitted && questions.length > 0 && (
          <span className="text-xs text-[#a3a3a3]">{questions.length} Fragen</span>
        )}
      </div>

      {questions.length === 0 ? (
        <div className="border border-dashed border-[#e5e5e5] rounded-lg p-8 text-center">
          <p className="text-sm text-[#a3a3a3]">Noch kein Test verfügbar</p>
        </div>
      ) : submitted ? (
        <div>
          <div className="border border-[#e5e5e5] rounded-lg p-6 text-center mb-6">
            <p className="text-3xl font-bold text-[#171717]">{getScore()}/{questions.length}</p>
            <p className="text-sm text-[#737373] mt-2">
              {getScore() === questions.length ? 'Perfekt!' :
               getScore() >= questions.length * 0.8 ? 'Sehr gut!' :
               getScore() >= questions.length * 0.6 ? 'Gut, aber übe weiter!' : 'Du musst mehr üben!'}
            </p>
          </div>

          <div className="space-y-3">
            {questions.map((q, i) => {
              const correct = isCorrectAnswer(answers[i] || '', q.answer)
              return (
                <div key={i} className={`p-4 rounded-lg border ${correct ? 'border-green-200 bg-green-50' : 'border-red-200 bg-red-50'}`}>
                  <p className="text-sm text-[#171717] font-medium">{q.question}</p>
                  <div className="mt-2 text-xs">
                    <span className={correct ? 'text-green-700' : 'text-red-700'}>
                      Deine Antwort: {answers[i] || '(leer)'}
                    </span>
                    {!correct && <span className="text-[#737373] ml-2">→ Richtig: {q.answer}</span>}
                  </div>
                </div>
              )
            })}
          </div>

          <div className="flex gap-3 mt-6">
            <button
              onClick={() => { setSubmitted(false); setAnswers({}) }}
              className="h-9 px-4 border border-[#e5e5e5] text-sm rounded-md hover:bg-[#f5f5f5] transition-colors"
            >
              Nochmal
            </button>
            <Link
              href={`/dashboard/${moduleSlug}/${topicId}/cards`}
              className="inline-flex items-center gap-2 h-9 px-4 bg-[#171717] text-white text-sm rounded-md hover:bg-[#2a2a2a] transition-colors"
            >
              Weiter zu Karten
              <ChevronRight size={14} />
            </Link>
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          {questions.map((q, i) => (
            <div key={i} className="border border-[#e5e5e5] rounded-lg p-4">
              <p className="text-sm font-medium text-[#171717] mb-3">
                <span className="text-[#a3a3a3] mr-2">{i + 1}.</span>
                {q.question}
              </p>
              {q.type === 'choose' && q.options ? (
                <div className="space-y-2">
                  {q.options.map((opt, j) => (
                    <label key={j} className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="radio"
                        name={`q${i}`}
                        value={opt}
                        checked={answers[i] === opt}
                        onChange={() => setAnswers(a => ({ ...a, [i]: opt }))}
                        className="accent-[#171717]"
                      />
                      <span className="text-sm text-[#525252]">{opt}</span>
                    </label>
                  ))}
                </div>
              ) : (
                <input
                  type="text"
                  value={answers[i] || ''}
                  onChange={e => setAnswers(a => ({ ...a, [i]: e.target.value }))}
                  placeholder="Antwort..."
                  className="w-full h-9 px-3 text-sm border border-[#e5e5e5] rounded-md focus:outline-none focus:border-[#171717] transition-colors"
                />
              )}
            </div>
          ))}
          <button
            onClick={handleSubmit}
            className="h-10 px-6 bg-[#171717] text-white text-sm font-medium rounded-md hover:bg-[#2a2a2a] transition-colors"
          >
            Test abgeben
          </button>
        </div>
      )}
    </div>
  )
}
