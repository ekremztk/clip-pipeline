'use client'

import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import { supabase } from '@/lib/supabase'
import Link from 'next/link'
import { ArrowLeft, Circle, CheckCircle2, Headphones, Eye, Mic, PenLine, RotateCcw, Volume2 } from 'lucide-react'

interface Task {
  id: string
  title: string
  description: string | null
  task_type: string | null
  is_completed: boolean
  due_date: string | null
}

const TASK_ICONS: Record<string, typeof Headphones> = {
  listen: Headphones,
  watch: Eye,
  speak: Mic,
  write: PenLine,
  review: RotateCcw,
  shadow: Volume2,
}

export default function TasksPage() {
  const params = useParams()
  const moduleSlug = params.moduleSlug as string
  const topicId = params.topicId as string
  const [tasks, setTasks] = useState<Task[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function load() {
      const { data } = await supabase
        .from('lern_tasks')
        .select('*')
        .eq('topic_id', topicId)
        .order('is_completed')
        .order('created_at')
      setTasks(data || [])
      setLoading(false)
    }
    load()
  }, [topicId])

  async function toggleTask(id: string, currentState: boolean) {
    await supabase
      .from('lern_tasks')
      .update({
        is_completed: !currentState,
        completed_at: !currentState ? new Date().toISOString() : null
      })
      .eq('id', id)
    setTasks(tasks.map(t => t.id === id ? { ...t, is_completed: !currentState } : t))
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

      <h1 className="text-2xl font-bold tracking-tight text-[#171717] mb-6">Görevler</h1>

      {tasks.length === 0 ? (
        <div className="border border-dashed border-[#e5e5e5] rounded-lg p-8 text-center">
          <p className="text-sm text-[#a3a3a3]">No tasks yet</p>
          <p className="text-xs text-[#a3a3a3] mt-1">Tasks will be assigned based on your progress</p>
        </div>
      ) : (
        <div className="space-y-2">
          {tasks.map(task => {
            const Icon = TASK_ICONS[task.task_type || ''] || Circle
            return (
              <div
                key={task.id}
                className={`flex items-start gap-3 p-4 border border-[#e5e5e5] rounded-lg transition-colors ${
                  task.is_completed ? 'opacity-60' : ''
                }`}
              >
                <button
                  onClick={() => toggleTask(task.id, task.is_completed)}
                  className="mt-0.5 flex-shrink-0"
                >
                  {task.is_completed ? (
                    <CheckCircle2 size={18} className="text-[#171717]" />
                  ) : (
                    <Circle size={18} className="text-[#e5e5e5] hover:text-[#737373] transition-colors" />
                  )}
                </button>
                <div className="flex-1">
                  <p className={`text-sm font-medium ${task.is_completed ? 'line-through text-[#a3a3a3]' : 'text-[#171717]'}`}>
                    {task.title}
                  </p>
                  {task.description && (
                    <p className="text-xs text-[#a3a3a3] mt-1">{task.description}</p>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  {task.task_type && (
                    <span className="flex items-center gap-1 text-xs text-[#a3a3a3]">
                      <Icon size={12} />
                      {task.task_type}
                    </span>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
