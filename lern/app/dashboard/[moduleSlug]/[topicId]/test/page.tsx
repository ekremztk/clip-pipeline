'use client'

import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import { supabase } from '@/lib/supabase'
import Link from 'next/link'
import { ArrowLeft, Clock } from 'lucide-react'

interface TestQuestion {
  question: string
  answer: string
  type: 'fill_blank' | 'translate' | 'choose'
  options?: string[]
  points: number
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
      if (answers[i]?.trim().toLowerCase() === q.answer.toLowerCase()) correct++
    })
    return correct
  }

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

      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold tracking-tight text-[#171717]">Test</h1>
        {!submitted && questions.length > 0 && (
          <span className="flex items-center gap-1 text-xs text-[#a3a3a3]">
            <Clock size={12} />
            {questions.length} questions
          </span>
        )}
      </div>

      {questions.length === 0 ? (
        <div className="border border-dashed border-[#e5e5e5] rounded-lg p-8 text-center">
          <p className="text-sm text-[#a3a3a3]">No test available yet</p>
          <p className="text-xs text-[#a3a3a3] mt-1">A test will be created when you&apos;re ready to close this topic</p>
        </div>
      ) : submitted ? (
        <div className="border border-[#e5e5e5] rounded-lg p-8 text-center">
          <p className="text-2xl font-bold text-[#171717]">{getScore()}/{questions.length}</p>
          <p className="text-sm text-[#737373] mt-2">
            {getScore() === questions.length ? 'Perfect!' :
             getScore() >= questions.length * 0.8 ? 'Great job!' :
             getScore() >= questions.length * 0.6 ? 'Keep practicing' : 'Review needed'}
          </p>
          <div className="mt-6 space-y-3 text-left">
            {questions.map((q, i) => {
              const isCorrect = answers[i]?.trim().toLowerCase() === q.answer.toLowerCase()
              return (
                <div key={i} className={`p-3 rounded-md border ${isCorrect ? 'border-green-200 bg-green-50' : 'border-red-200 bg-red-50'}`}>
                  <p className="text-sm text-[#171717]">{q.question}</p>
                  <p className="text-xs mt-1">
                    Your answer: <span className={isCorrect ? 'text-green-700' : 'text-red-700'}>{answers[i] || '(empty)'}</span>
                    {!isCorrect && <span className="text-[#737373]"> → {q.answer}</span>}
                  </p>
                </div>
              )
            })}
          </div>
          <button
            onClick={() => { setSubmitted(false); setAnswers({}) }}
            className="mt-6 h-9 px-4 bg-[#171717] text-white text-sm rounded-md hover:bg-[#2a2a2a] transition-colors"
          >
            Retry
          </button>
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
                      <span className="text-sm text-[#737373]">{opt}</span>
                    </label>
                  ))}
                </div>
              ) : (
                <input
                  type="text"
                  value={answers[i] || ''}
                  onChange={e => setAnswers(a => ({ ...a, [i]: e.target.value }))}
                  placeholder="Answer..."
                  className="w-full h-9 px-3 text-sm border border-[#e5e5e5] rounded-md focus:outline-none focus:border-[#171717]"
                />
              )}
            </div>
          ))}
          <button
            onClick={handleSubmit}
            className="h-9 px-6 bg-[#171717] text-white text-sm font-medium rounded-md hover:bg-[#2a2a2a] transition-colors"
          >
            Submit Test
          </button>
        </div>
      )}
    </div>
  )
}
