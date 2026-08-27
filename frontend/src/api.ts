/**
 * 后端 API 调用封装
 */

const BASE = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '');
const ACCESS_TOKEN_KEY = 'douyinmind_access_token';

export function getAccessToken(): string {
  return localStorage.getItem(ACCESS_TOKEN_KEY) || '';
}

export function setAccessToken(token: string): void {
  const value = token.trim();
  if (value) localStorage.setItem(ACCESS_TOKEN_KEY, value);
  else localStorage.removeItem(ACCESS_TOKEN_KEY);
}

export function apiUrl(path: string): string {
  return `${BASE}${path}`;
}

function headers(): HeadersInit {
  const token = getAccessToken();
  return token ? { 'X-DouyinMind-Token': token } : {};
}

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(apiUrl(url), {
    headers: { 'Content-Type': 'application/json', ...headers() },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => 'Unknown error');
    throw new Error(`${res.status}: ${text}`);
  }
  return res.json();
}

// ---- Auth ----

export async function loginStart(): Promise<{ success: boolean; message: string; status: string }> {
  return request('/auth/douyin/login/start', { method: 'POST' });
}

export async function loginStatus(): Promise<{ status: string; message: string }> {
  return request('/auth/douyin/login/status');
}

export async function loginQr(): Promise<Blob> {
  const res = await fetch(apiUrl('/auth/douyin/login/qr'), {
    headers: headers(),
    cache: 'no-store',
  });
  if (!res.ok) throw new Error(`${res.status}: QR code not ready`);
  return res.blob();
}

export async function logout(): Promise<{ success: boolean; message: string }> {
  return request('/auth/douyin/logout', { method: 'POST' });
}

// ---- Favorites ----

export async function syncFavorites(): Promise<{
  success: boolean;
  collections_total?: number;
  videos_total?: number;
  added_videos?: number;
  removed_videos?: number;
  message?: string;
}> {
  return request('/favorites/sync', { method: 'POST' });
}

export async function listCollections(): Promise<{ success: boolean; items: CollectionItem[]; total: number }> {
  return request('/favorites/collections');
}

export async function listCollectionVideos(
  collectionId: string, page = 1, size = 20
): Promise<{ success: boolean; items: VideoItem[]; total: number }> {
  return request(`/favorites/collections/${collectionId}/videos?page=${page}&size=${size}`);
}

// ---- Knowledge ----

export async function syncKnowledge(selectedIds?: string[]): Promise<{ success: boolean; task_id?: string; pending_count?: number; message?: string }> {
  return request('/knowledge/sync', {
    method: 'POST',
    body: JSON.stringify({ selected_ids: selectedIds || [] }),
  });
}

export async function resetFailedVideos(): Promise<{ success: boolean; reset_count: number }> {
  return request('/knowledge/reset-failed', { method: 'POST' });
}

export async function deleteVideo(platformItemId: string): Promise<{ success: boolean; message?: string }> {
  return request(`/knowledge/videos/${platformItemId}`, { method: 'DELETE' });
}

export async function getSyncProgress(taskId: string): Promise<any> {
  return request(`/knowledge/sync/${taskId}`);
}

export async function getKnowledgeStats(): Promise<any> {
  return request('/knowledge/stats');
}

// ---- Chat ----

export async function chatAsk(query: string, sessionId?: number | null, collectionId?: string | null): Promise<{
  success: boolean;
  answer?: string;
  sources?: SourceItem[];
  session_id?: number;
  route_type?: string;
  latency_ms?: number;
  message?: string;
}> {
  return request('/chat/ask', {
    method: 'POST',
    body: JSON.stringify({ query, session_id: sessionId ?? null, collection_id: collectionId ?? null }),
  });
}

export async function* chatAskStream(query: string, sessionId?: number | null): AsyncGenerator<any> {
  const res = await fetch(apiUrl('/chat/ask/stream'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...headers() },
    body: JSON.stringify({ query, session_id: sessionId ?? null }),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  if (!res.body) throw new Error('No stream body');

  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();

  let eventType = '';
  let dataBuffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    const chunk: string = value;
    const lines = chunk.split('\n');

    for (const line of lines) {
      if (line.startsWith('event: ')) {
        eventType = line.slice(7).trim();
      } else if (line.startsWith('data: ')) {
        dataBuffer += line.slice(6);
      } else if (line === '' && dataBuffer) {
        // Empty line = end of event, flush
        try {
          const data = JSON.parse(dataBuffer);
          yield { ...data, _event: eventType };
        } catch {}
        eventType = '';
        dataBuffer = '';
      }
    }
  }
}

export async function listSessions(): Promise<{ success: boolean; items: SessionItem[] }> {
  return request('/chat/sessions');
}

export async function getSessionMessages(sessionId: number): Promise<{ success: boolean; items: MessageItem[] }> {
  return request(`/chat/sessions/${sessionId}/messages`);
}

export async function deleteSession(sessionId: number): Promise<{ success: boolean }> {
  return request(`/chat/sessions/${sessionId}`, { method: 'DELETE' });
}

// ---- Types ----

export interface CollectionItem {
  id: number;
  collection_id: string;
  title: string;
  video_count: number;
  is_active: boolean;
}

export interface VideoItem {
  id: number;
  collection_id: string;
  platform_item_id: string;
  url: string;
  title: string;
  author: string;
  duration: number;
  status: string;
}

export interface SourceItem {
  platform_item_id: string;
  title: string;
  url: string;
  score: number;
}

export interface SessionItem {
  id: number;
  title: string;
  message_count: number;
  last_message_at: string | null;
  created_at: string;
}

export interface MessageItem {
  id: number;
  session_id: number;
  role: 'user' | 'assistant';
  content: string;
  route_type: string;
  created_at: string;
}
