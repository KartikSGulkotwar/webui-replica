import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { errorMessage } from '../api/client'
import { shareConversation, unshareConversation } from '../api/conversations'
import { conversationKey } from '../hooks/useConversation'
import { conversationsKey, useUpdateConversation } from '../hooks/useConversations'
import { conversationToMarkdown, downloadFile, safeFilename } from '../lib/exportChat'
import type { ConversationDetail } from '../types/api'
import Dialog from './Dialog'
import {
  ArchiveIcon,
  CheckIcon,
  CopyIcon,
  DotsIcon,
  DownloadIcon,
  InstructionsIcon,
  PinIcon,
  ShareIcon,
} from './icons'

const item =
  'flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm hover:bg-zinc-100 dark:hover:bg-zinc-800'
const button =
  'rounded-lg border border-zinc-300 px-3 py-1.5 text-sm hover:bg-zinc-100 disabled:opacity-50 dark:border-zinc-700 dark:hover:bg-zinc-800'
const primary =
  'rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50'

export function SystemPromptDialog({
  value,
  onSave,
  onClose,
  saving,
  error,
}: {
  value: string
  onSave: (text: string) => void
  onClose: () => void
  saving?: boolean
  error?: unknown
}) {
  const [text, setText] = useState(value)
  return (
    <Dialog title="System prompt" onClose={onClose}>
      <p className="mb-2 text-sm text-zinc-500">
        Instructions the model follows for this whole chat, e.g. “Answer in short bullet points” or
        “You are a patient Python tutor”.
      </p>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={6}
        maxLength={10000}
        autoFocus
        aria-label="Instructions for the model"
        className="w-full rounded-lg border border-zinc-300 bg-white p-2 text-sm outline-none focus:border-indigo-500 dark:border-zinc-700 dark:bg-zinc-950"
      />
      {error ? <p className="mt-2 text-sm text-red-500">{errorMessage(error)}</p> : null}
      <div className="mt-3 flex justify-end gap-2">
        {value && (
          <button type="button" className={`${button} mr-auto`} onClick={() => onSave('')}>
            Clear
          </button>
        )}
        <button type="button" className={button} onClick={onClose}>
          Cancel
        </button>
        <button
          type="button"
          className={primary}
          disabled={saving}
          onClick={() => onSave(text.trim())}
        >
          Save
        </button>
      </div>
    </Dialog>
  )
}

function ShareDialog({
  conversation,
  onClose,
}: {
  conversation: ConversationDetail
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const [copied, setCopied] = useState(false)
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: conversationKey(conversation.id) })
    queryClient.invalidateQueries({ queryKey: conversationsKey })
  }
  // The current link, updated from each response (the conversation prop can be stale).
  const [shareId, setShareId] = useState(conversation.share_id)
  const share = useMutation({
    mutationFn: () => shareConversation(conversation.id),
    onSuccess: (data) => {
      setShareId(data.share_id)
      refresh()
    },
  })
  const unshare = useMutation({
    mutationFn: () => unshareConversation(conversation.id),
    onSuccess: () => {
      setShareId(null)
      share.reset()
      refresh()
    },
  })
  const url = shareId ? `${window.location.origin}/s/${shareId}` : ''
  const error = share.error ?? unshare.error

  return (
    <Dialog title="Share chat" onClose={onClose}>
      {shareId ? (
        <div className="space-y-3">
          <p className="text-sm text-zinc-500">
            Anyone with this link can read the chat as it is now. Messages you add later stay
            private until you update the link.
          </p>
          <div className="flex gap-2">
            <input
              readOnly
              value={url}
              aria-label="Share link"
              onFocus={(e) => e.target.select()}
              className="min-w-0 flex-1 rounded-lg border border-zinc-300 bg-zinc-50 px-2 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-950"
            />
            <button
              type="button"
              className={primary}
              onClick={async () => {
                await navigator.clipboard.writeText(url).catch(() => {})
                setCopied(true)
                setTimeout(() => setCopied(false), 1500)
              }}
            >
              <span className="flex items-center gap-1">
                {copied ? (
                  <CheckIcon width={14} height={14} />
                ) : (
                  <CopyIcon width={14} height={14} />
                )}
                {copied ? 'Copied' : 'Copy'}
              </span>
            </button>
          </div>
          <div className="flex justify-between gap-2">
            <button
              type="button"
              className={button}
              disabled={unshare.isPending}
              onClick={() => unshare.mutate()}
            >
              Stop sharing
            </button>
            <button
              type="button"
              className={button}
              disabled={share.isPending}
              onClick={() => share.mutate()}
            >
              {share.isSuccess ? 'Link updated' : 'Update with latest messages'}
            </button>
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          <p className="text-sm text-zinc-500">
            Create a public, read-only link to this chat. Your system prompt isn’t included.
          </p>
          <button
            type="button"
            className={primary}
            disabled={share.isPending}
            onClick={() => share.mutate()}
          >
            Create link
          </button>
        </div>
      )}
      {error ? <p className="mt-2 text-sm text-red-500">{errorMessage(error)}</p> : null}
    </Dialog>
  )
}

interface Props {
  conversation: ConversationDetail | undefined
  /** For a chat that doesn't exist yet: its system prompt is kept until the first message. */
  draftSystemPrompt: string
  onDraftSystemPrompt: (text: string) => void
  modelLabel: (id: string) => string
}

export default function ChatMenu({
  conversation,
  draftSystemPrompt,
  onDraftSystemPrompt,
  modelLabel,
}: Props) {
  const [open, setOpen] = useState(false)
  const [dialog, setDialog] = useState<'system' | 'share' | null>(null)
  const ref = useRef<HTMLDivElement>(null)
  const update = useUpdateConversation()
  const navigate = useNavigate()

  useEffect(() => {
    if (!open) return
    const close = (e: PointerEvent) => !ref.current?.contains(e.target as Node) && setOpen(false)
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('pointerdown', close)
    document.addEventListener('keydown', esc)
    return () => {
      document.removeEventListener('pointerdown', close)
      document.removeEventListener('keydown', esc)
    }
  }, [open])

  const pick = (fn: () => void) => () => {
    setOpen(false)
    fn()
  }
  const hasPrompt = !!(conversation ? conversation.system_prompt : draftSystemPrompt)

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className={`rounded-lg p-2 hover:bg-zinc-100 dark:hover:bg-zinc-800 ${
          hasPrompt
            ? 'text-indigo-500'
            : 'text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100'
        }`}
        aria-label="Chat options"
        aria-haspopup="menu"
        aria-expanded={open}
        title={hasPrompt ? 'Chat options (system prompt set)' : 'Chat options'}
      >
        <DotsIcon />
      </button>
      {open && (
        <div
          role="menu"
          className="absolute right-0 z-20 mt-1 w-56 rounded-lg border border-zinc-200 bg-white p-1 shadow-lg dark:border-zinc-700 dark:bg-zinc-900"
        >
          <button
            type="button"
            role="menuitem"
            className={item}
            onClick={pick(() => setDialog('system'))}
          >
            <InstructionsIcon /> System prompt{hasPrompt ? ' (set)' : ''}
          </button>
          {conversation && (
            <>
              <button
                type="button"
                role="menuitem"
                className={item}
                onClick={pick(() => setDialog('share'))}
              >
                <ShareIcon /> {conversation.share_id ? 'Shared link' : 'Share'}
              </button>
              <button
                type="button"
                role="menuitem"
                className={item}
                onClick={pick(() =>
                  downloadFile(
                    `${safeFilename(conversation.title)}.md`,
                    conversationToMarkdown(conversation, modelLabel),
                    'text/markdown',
                  ),
                )}
              >
                <DownloadIcon /> Export as Markdown
              </button>
              <button
                type="button"
                role="menuitem"
                className={item}
                onClick={pick(() =>
                  downloadFile(
                    `${safeFilename(conversation.title)}.json`,
                    JSON.stringify(conversation, null, 2),
                    'application/json',
                  ),
                )}
              >
                <DownloadIcon /> Export as JSON
              </button>
              <button
                type="button"
                role="menuitem"
                className={item}
                onClick={pick(() =>
                  update.mutate({ id: conversation.id, patch: { pinned: !conversation.pinned } }),
                )}
              >
                <PinIcon /> {conversation.pinned ? 'Unpin' : 'Pin'}
              </button>
              <button
                type="button"
                role="menuitem"
                className={item}
                onClick={pick(() => {
                  update.mutate({ id: conversation.id, patch: { archived: true } })
                  navigate('/')
                })}
              >
                <ArchiveIcon /> Archive
              </button>
            </>
          )}
        </div>
      )}

      {dialog === 'system' && (
        <SystemPromptDialog
          value={(conversation ? conversation.system_prompt : draftSystemPrompt) ?? ''}
          saving={update.isPending}
          error={update.error}
          onClose={() => setDialog(null)}
          onSave={(text) => {
            if (!conversation) {
              onDraftSystemPrompt(text)
              setDialog(null)
              return
            }
            update.mutate(
              { id: conversation.id, patch: { system_prompt: text } },
              { onSuccess: () => setDialog(null) },
            )
          }}
        />
      )}
      {dialog === 'share' && conversation && (
        <ShareDialog conversation={conversation} onClose={() => setDialog(null)} />
      )}
    </div>
  )
}
