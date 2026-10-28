import { useEffect, useRef } from 'react'

import { apiUrl, getToken } from '../api'

interface Options {
  requestId?: string | null
  enabled?: boolean
  onUpdate: () => void
}

/**
 * Subscribes to the sales BFF approval SSE stream.
 *
 * A plain EventSource cannot attach the localStorage bearer token, so this
 * hook uses a fetch stream instead: it can send the bearer token when present,
 * still sends same-origin cookies in EAI mode, and falls back to polling if
 * the stream is unavailable (local token-only mode, proxy restart, network).
 */
export function useApprovalStream({ requestId, enabled = true, onUpdate }: Options): void {
  const callback = useRef(onUpdate)
  callback.current = onUpdate

  useEffect(() => {
    if (!enabled) return
    let disposed = false
    let controller: AbortController | null = null
    let pollTimer: number | null = null
    let reconnectTimer: number | null = null

    const startPolling = () => {
      if (pollTimer !== null || disposed) return
      callback.current()
      pollTimer = window.setInterval(() => callback.current(), 8000)
    }

    const stopPolling = () => {
      if (pollTimer !== null) {
        window.clearInterval(pollTimer)
        pollTimer = null
      }
    }

    const scheduleReconnect = () => {
      if (reconnectTimer !== null || disposed) return
      reconnectTimer = window.setTimeout(() => {
        reconnectTimer = null
        void connect()
      }, 30000)
    }

    const consume = async (response: Response) => {
      if (!response.ok || !response.body) throw new Error(`SSE ${response.status}`)
      stopPolling()
      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      while (!disposed) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const chunks = buffer.split('\n\n')
        buffer = chunks.pop() ?? ''
        for (const chunk of chunks) {
          if (chunk.includes('event:') || chunk.includes('data:')) callback.current()
        }
      }
    }

    const connect = async () => {
      if (disposed) return
      controller?.abort()
      controller = new AbortController()
      const path = requestId
        ? `/approvals/${encodeURIComponent(requestId)}/stream`
        : '/approvals/stream'
      const headers = new Headers()
      const token = getToken()
      if (token) headers.set('Authorization', `Bearer ${token}`)
      try {
        const response = await fetch(apiUrl(path), {
          headers,
          credentials: 'include',
          cache: 'no-store',
          signal: controller.signal,
        })
        await consume(response)
        if (!disposed) {
          startPolling()
          scheduleReconnect()
        }
      } catch (error) {
        if (disposed || (error instanceof DOMException && error.name === 'AbortError')) return
        startPolling()
        scheduleReconnect()
      }
    }

    void connect()
    return () => {
      disposed = true
      controller?.abort()
      stopPolling()
      if (reconnectTimer !== null) window.clearTimeout(reconnectTimer)
    }
  }, [enabled, requestId])
}
