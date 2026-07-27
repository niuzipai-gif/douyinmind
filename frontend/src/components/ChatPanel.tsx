import { useState, useRef, useEffect, FormEvent } from 'react';
import * as api from '../api';
import ExecutionTrace from './ExecutionTrace';

interface Props { collectionId: string; statsRefreshKey: number; }

interface TraceData {
  route: string;
  steps: { name: string; time_ms: number }[];
  chunks: { chunk_id: string; title: string; text: string; score: number }[];
}

interface Message {
  role: 'user' | 'assistant' | 'system';
  content: string;
  sources?: api.SourceItem[];
  isStreaming?: boolean;
  trace?: TraceData;
  latency_ms?: number;
}

export default function ChatPanel({ collectionId }: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState<number | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages]);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const q = input.trim();
    if (!q || loading) return;
    setInput('');
    setLoading(true);

    // Add user message
    const userMsg: Message = { role: 'user', content: q };
    setMessages(prev => [...prev, userMsg]);

    // Add placeholder for assistant
    const assistantMsg: Message = { role: 'assistant', content: '', isStreaming: true };
    setMessages(prev => [...prev, assistantMsg]);

    try {
      // 直接用非流式（绕过 SSE 前端解析问题）
      const r = await api.chatAsk(q, sessionId, collectionId);
      if (r.success && r.answer) {
        setMessages(prev => prev.map(m =>
          m.role === 'assistant' && m.isStreaming
            ? { role: 'assistant' as const, content: r.answer!, sources: r.sources, isStreaming: false, trace: (r as any).trace, latency_ms: r.latency_ms }
            : m
        ));
        if (r.session_id) setSessionId(r.session_id);
      } else {
        setMessages(prev => prev.map(m =>
          m.role === 'assistant' && m.isStreaming
            ? { role: 'system' as const, content: r.message || '请求失败', isStreaming: false }
            : m
        ));
      }
    } catch {
      setMessages(prev => prev.map(m =>
        m.role === 'assistant' && m.isStreaming
          ? { role: 'system' as const, content: '抱歉，请求失败，请稍后重试。', isStreaming: false }
          : m
      ));
    }

    setMessages(prev => prev.map(m => ({ ...m, isStreaming: false })));
    setLoading(false);
  };

  const promptChips = ['💡 最近收藏了什么好内容？', '📝 帮我总结技术类视频的要点', '🔍 有哪些关于AI的视频？'];

  return (
    <div className="h-full flex flex-col bg-[var(--color-panel)]">
      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-6">
        {messages.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center gap-6 text-center">
            <div className="w-[72px] h-[72px] rounded-full flex items-center justify-center bg-gradient-to-br from-accent to-amber shadow-xl shadow-accent/15">
              <span className="text-3xl">🧠</span>
            </div>
            <div>
              <h2 className="font-display text-xl text-[var(--color-ink)]">你的收藏夹知识库</h2>
              <p className="text-sm text-[var(--color-ink-muted)] mt-1">登录 → 同步收藏夹 → 一键入库 → 开始对话</p>
            </div>
            <div className="flex flex-wrap gap-2 justify-center max-w-md">
              {promptChips.map((text, i) => (
                <button key={i} onClick={() => setInput(text)} className="px-4 py-2.5 rounded-xl text-sm transition-all hover:shadow-sm"
                  style={{ backgroundColor: i === 0 ? 'rgba(232,89,74,0.08)' : i === 1 ? 'rgba(212,148,58,0.08)' : 'rgba(0,0,0,0.04)' }}>
                  <span style={{ color: i === 0 ? 'var(--color-accent)' : i === 1 ? 'var(--color-amber)' : 'var(--color-ink-soft)' }}>{text}</span>
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="flex flex-col gap-5 max-w-3xl mx-auto">
            {messages.map((msg, i) => (
              <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div className={`max-w-[78%] px-4 py-3 rounded-2xl text-sm leading-relaxed ${
                  msg.role === 'user'
                    ? 'bg-gradient-to-r from-accent to-accent-hover text-white'
                    : msg.role === 'system'
                      ? 'bg-red-50 text-red-600 border border-red-100'
                      : 'bg-white/80 border border-[var(--color-border)] text-[var(--color-ink)]'
                }`}>
                  {msg.content}
                  {msg.isStreaming && <span className="inline-block w-1.5 h-4 bg-current ml-0.5 animate-pulse rounded-sm" />}
                  {/* Execution Trace */}
                  {msg.trace && <ExecutionTrace trace={msg.trace} latency_ms={msg.latency_ms} />}
                  {/* Sources */}
                  {msg.sources && msg.sources.length > 0 && (
                    <div className="mt-3 pt-3 border-t border-dashed border-black/10">
                      <span className="text-[11px] text-[var(--color-ink-muted)]">📎 来源：</span>
                      {msg.sources.map((s, j) => (
                        <a key={j} href={s.url} target="_blank" rel="noopener noreferrer"
                          className="block mt-1 px-2 py-1 rounded-lg text-xs text-accent bg-accent-light hover:underline">
                          {s.title} (相关度: {s.score.toFixed(2)})
                        </a>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Input */}
      <form onSubmit={handleSubmit} className="flex items-center gap-3 px-5 py-4 border-t border-[var(--color-border)]">
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          placeholder="输入你的问题，搜索收藏夹中的知识..."
          className="flex-1 h-12 px-5 rounded-2xl border border-[var(--color-border)] bg-white/90 text-sm outline-none
                     focus:border-accent/50 focus:ring-4 focus:ring-accent/10 transition-all
                     placeholder:text-[var(--color-ink-muted)]"
          disabled={loading}
        />
        <button type="submit" disabled={loading || !input.trim()}
          className="w-12 h-12 rounded-2xl flex items-center justify-center bg-gradient-to-r from-accent to-accent-hover text-white text-xl font-bold
                     shadow-md shadow-accent/20 hover:shadow-lg disabled:opacity-40 transition-all flex-shrink-0">
          {loading ? '⋯' : '→'}
        </button>
      </form>
    </div>
  );
}
