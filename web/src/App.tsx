import { useState, useRef, FormEvent } from 'react'
import { Send } from 'lucide-react'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

interface Source {
  source: string
  distance: number
}

interface Record {
  id: number
  number: number
  question: string
  answer: string
  sources: Source[]
  status: 'streaming' | 'done' | 'error'
  timestamp: Date
  errorMessage?: string
}

interface DeltaPayload {
  delta: string
}

interface DonePayload {
  done: true
  formatted_answer: string
  sources: Source[]
}

type StreamPayload = DeltaPayload | DonePayload

function isDonePayload(payload: StreamPayload): payload is DonePayload {
  return 'done' in payload
}

// Turns "[text](url)" into real links; everything else stays as plain text.
// Deliberately narrow — we only need to handle the citation format our API
// produces, not general markdown.
function renderAnswerText(text: string) {
  const parts: (string | JSX.Element)[] = []
  const pattern = /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g
  let lastIndex = 0
  let match: RegExpExecArray | null

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index))
    }
    parts.push(
      <a
        key={match.index}
        href={match[2]}
        target="_blank"
        rel="noopener noreferrer"
        className="text-brass underline decoration-brass/40 underline-offset-2 hover:decoration-brass"
      >
        {match[1]}
      </a>
    )
    lastIndex = pattern.lastIndex
  }
  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex))
  }
  return parts
}

function formatTime(date: Date) {
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function RecordEntry({ record }: { record: Record }) {
  return (
    <div className="border-l-2 border-rule pl-5 py-1">
      <div className="flex items-baseline justify-between mb-2">
        <span className="font-mono text-xs text-ink-soft tracking-wide">
          No. {String(record.number).padStart(3, '0')}
        </span>
        <span className="font-mono text-xs text-ink-soft">
          {formatTime(record.timestamp)}
        </span>
      </div>

      <p className="font-serif text-lg leading-snug mb-3">{record.question}</p>

      <div className="text-[15px] leading-relaxed whitespace-pre-wrap mb-3">
        {record.status === 'error' ? (
          <span className="text-red-800">{record.errorMessage}</span>
        ) : (
          renderAnswerText(record.answer)
        )}
        {record.status === 'streaming' && (
          <span className="inline-block w-1.5 h-4 bg-ink align-middle ml-0.5 animate-pulse" />
        )}
      </div>

      {record.sources.length > 0 && (
        <div className="border-t border-rule pt-2 mt-2">
          <p className="font-mono text-xs text-ink-soft mb-1">Sources</p>
          <ul className="text-xs text-ink-soft space-y-0.5">
            {record.sources.map((s, i) => (
              <li key={i} className="flex items-center gap-1">
                <span>{i + 1}.</span>
                <span>{s.source}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

export default function App() {
  const [records, setRecords] = useState<Record[]>([])
  const [input, setInput] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const recordCounter = useRef(0)

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const question = input.trim()
    if (!question || isSubmitting) return

    recordCounter.current += 1
    const recordId = recordCounter.current

    const newRecord: Record = {
      id: recordId,
      number: recordId,
      question,
      answer: '',
      sources: [],
      status: 'streaming',
      timestamp: new Date(),
    }

    setRecords((prev) => [newRecord, ...prev])
    setInput('')
    setIsSubmitting(true)

    try {
      const response = await fetch(`${API_URL}/ask/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question }),
      })

      if (!response.ok || !response.body) {
        throw new Error(`Request failed (${response.status})`)
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { value, done } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n\n')
        buffer = lines.pop() ?? ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const payload: StreamPayload = JSON.parse(line.slice(6))

          if (isDonePayload(payload)) {
            setRecords((prev) =>
              prev.map((r) =>
                r.id === recordId
                  ? {
                      ...r,
                      answer: payload.formatted_answer,
                      sources: payload.sources,
                      status: 'done',
                    }
                  : r
              )
            )
          } else {
            setRecords((prev) =>
              prev.map((r) =>
                r.id === recordId ? { ...r, answer: r.answer + payload.delta } : r
              )
            )
          }
        }
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err)
      setRecords((prev) =>
        prev.map((r) =>
          r.id === recordId
            ? {
                ...r,
                status: 'error',
                errorMessage: `Something went wrong: ${message}. Is the API running on localhost:8000?`,
              }
            : r
        )
      )
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="min-h-screen bg-paper font-sans text-ink">
      <div className="max-w-[680px] mx-auto px-6 py-12">
        <header className="border-b-2 border-ink pb-4 mb-8">
          <h1 className="font-serif text-[28px] leading-none mb-1.5">
            Tax Law Assistant
          </h1>
          <p className="text-sm text-ink-soft">
            Federal income tax reference, from IRS Publication 17 and Title
            26. General information only, not personalized tax advice.
          </p>
        </header>

        <form onSubmit={handleSubmit} className="flex gap-2 mb-10">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask a federal income tax question…"
            className="flex-1 bg-surface border border-rule px-4 py-3 text-[15px] focus:outline-none focus:border-accent placeholder:text-ink-soft/70"
          />
          <button
            type="submit"
            disabled={isSubmitting}
            className="flex items-center gap-2 px-5 py-3 bg-accent text-surface text-[15px] disabled:bg-ink-soft disabled:cursor-default"
          >
            <Send size={15} />
            Ask
          </button>
        </form>

        {records.length === 0 ? (
          <p className="text-ink-soft text-sm">
            No questions asked yet. Try "What is the standard deduction?"
          </p>
        ) : (
          <div className="space-y-8">
            {records.map((record) => (
              <RecordEntry key={record.id} record={record} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}