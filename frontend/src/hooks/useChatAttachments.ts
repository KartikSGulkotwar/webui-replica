import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { errorMessage } from '../api/client'
import { setAttachments, uploadDocument } from '../api/knowledge'
import type { Attachment, ConversationDetail } from '../types/api'
import { conversationKey } from './useConversation'

interface Upload {
  key: string
  name: string
  error?: string
}

/**
 * What a chat retrieves from: knowledge bases and single uploaded files. For a
 * chat that doesn't exist yet the choice is held locally and sent when the
 * first message creates it.
 */
export function useChatAttachments(
  conversation: ConversationDetail | undefined,
  maxUploadMb: number,
) {
  const queryClient = useQueryClient()
  const [draft, setDraft] = useState<Attachment[]>([])
  const [uploads, setUploads] = useState<Upload[]>([])
  const [error, setError] = useState<string | null>(null)
  const attachments = conversation ? conversation.attachments : draft
  // upload() awaits; it must read the latest draft, not the one from when it started.
  const draftRef = useRef(draft)
  draftRef.current = draft

  // Starting a new chat clears the previous draft.
  useEffect(() => {
    if (conversation) setDraft([])
  }, [conversation])

  const apply = async (next: Attachment[]) => {
    setError(null)
    if (!conversation) {
      setDraft(next)
      return
    }
    const key = conversationKey(conversation.id)
    const previous = queryClient.getQueryData<ConversationDetail>(key)
    queryClient.setQueryData<ConversationDetail>(key, (d) => (d ? { ...d, attachments: next } : d))
    try {
      const saved = await setAttachments(conversation.id, {
        collection_ids: next.filter((a) => a.kind === 'collection').map((a) => a.id),
        document_ids: next.filter((a) => a.kind === 'document').map((a) => a.id),
      })
      queryClient.setQueryData<ConversationDetail>(key, (d) =>
        d ? { ...d, attachments: saved } : d,
      )
    } catch (err) {
      if (previous) queryClient.setQueryData(key, previous)
      setError(errorMessage(err))
    }
  }

  const toggle = (item: Attachment) => {
    const has = attachments.some((a) => a.kind === item.kind && a.id === item.id)
    apply(
      has
        ? attachments.filter((a) => !(a.kind === item.kind && a.id === item.id))
        : [...attachments, item],
    )
  }

  const remove = (item: Attachment) =>
    apply(attachments.filter((a) => !(a.kind === item.kind && a.id === item.id)))

  const upload = async (files: FileList | File[]) => {
    const added: Attachment[] = []
    for (const file of Array.from(files)) {
      const key = `${file.name}-${file.size}-${Date.now()}`
      if (file.size > maxUploadMb * 1024 * 1024) {
        setUploads((u) => [...u, { key, name: file.name, error: `Larger than ${maxUploadMb} MB` }])
        continue
      }
      setUploads((u) => [...u, { key, name: file.name }])
      try {
        const doc = await uploadDocument(file)
        added.push({ kind: 'document', id: doc.id, name: doc.filename })
        setUploads((u) => u.filter((x) => x.key !== key))
      } catch (err) {
        setUploads((u) => u.map((x) => (x.key === key ? { ...x, error: errorMessage(err) } : x)))
      }
    }
    if (added.length)
      await apply([...(conversation ? conversation.attachments : draftRef.current), ...added])
  }

  const dismissUpload = (key: string) => setUploads((u) => u.filter((x) => x.key !== key))
  const busy = uploads.some((u) => !u.error)

  return { attachments, uploads, error, toggle, remove, upload, dismissUpload, busy, draft }
}

export type AttachmentControls = ReturnType<typeof useChatAttachments>
