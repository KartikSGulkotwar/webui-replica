import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { errorMessage } from '../api/client'
import {
  createCustomModel,
  deleteCustomModel,
  listCustomModels,
  updateCustomModel,
} from '../api/customModels'
import { PlusIcon } from '../components/icons'
import PageHeader from '../components/PageHeader'
import { useMe } from '../hooks/useAuth'
import { useDocumentTitle } from '../hooks/useDocumentTitle'
import { useCollections } from '../hooks/useKnowledge'
import { useModels } from '../hooks/useModels'
import type { CustomModel, CustomModelInput } from '../types/api'

const input =
  'w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm outline-none focus:border-indigo-500 dark:border-zinc-700 dark:bg-zinc-950'
const label = 'mb-1 block text-sm font-medium'
const button =
  'rounded-lg border border-zinc-300 px-3 py-1.5 text-sm hover:bg-zinc-100 disabled:opacity-50 dark:border-zinc-700 dark:hover:bg-zinc-800'
const EMOJIS = ['🤖', '📘', '🧑‍💼', '🧑‍🏫', '💻', '✍️', '🔬', '⚖️', '🩺', '🌍']

const key = ['custom-models'] as const

function Editor({ model, onDone }: { model?: CustomModel; onDone: () => void }) {
  const me = useMe()
  const models = useModels()
  const collections = useCollections()
  const queryClient = useQueryClient()
  const [form, setForm] = useState<CustomModelInput>({
    name: model?.name ?? '',
    description: model?.description ?? '',
    emoji: model?.emoji ?? '🤖',
    base_model_id: model?.base_model_id ?? '',
    system_prompt: model?.system_prompt ?? '',
    knowledge_ids: model?.knowledge.map((k) => k.id) ?? [],
    visibility: model?.visibility ?? 'private',
  })
  const set = <K extends keyof CustomModelInput>(k: K, v: CustomModelInput[K]) =>
    setForm((f) => ({ ...f, [k]: v }))
  const save = useMutation({
    mutationFn: () => (model ? updateCustomModel(model.id, form) : createCustomModel(form)),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: key })
      queryClient.invalidateQueries({ queryKey: ['models'] })
      onDone()
    },
  })
  const baseModels = (models.data?.models ?? []).filter((m) => m.provider_kind !== 'custom')
  // Knowledge bases are the creator's own; editing someone else's public model keeps its list.
  const ownKnowledge = !model || model.is_owner

  return (
    <form
      onSubmit={(e: FormEvent) => {
        e.preventDefault()
        save.mutate()
      }}
      className="space-y-4 rounded-xl border border-zinc-200 bg-zinc-50 p-4 dark:border-zinc-800 dark:bg-zinc-900"
    >
      <h3 className="font-semibold">{model ? `Edit ${model.name}` : 'New custom model'}</h3>
      <div className="flex gap-3">
        <div>
          <span className={label}>Icon</span>
          <select
            value={form.emoji}
            onChange={(e) => set('emoji', e.target.value)}
            aria-label="Icon"
            className="rounded-lg border border-zinc-300 bg-white px-2 py-2 text-lg dark:border-zinc-700 dark:bg-zinc-950"
          >
            {[...new Set([form.emoji, ...EMOJIS])].map((e) => (
              <option key={e} value={e}>
                {e}
              </option>
            ))}
          </select>
        </div>
        <div className="flex-1">
          <label htmlFor="cm-name" className={label}>
            Name
          </label>
          <input
            id="cm-name"
            value={form.name}
            onChange={(e) => set('name', e.target.value)}
            required
            maxLength={100}
            placeholder="e.g. HR Helper"
            className={input}
          />
        </div>
      </div>
      <div>
        <label htmlFor="cm-desc" className={label}>
          Description
        </label>
        <input
          id="cm-desc"
          value={form.description}
          onChange={(e) => set('description', e.target.value)}
          maxLength={500}
          placeholder="Shown in the model menu"
          className={input}
        />
      </div>
      <div>
        <label htmlFor="cm-base" className={label}>
          Base model
        </label>
        <select
          id="cm-base"
          value={form.base_model_id}
          onChange={(e) => set('base_model_id', e.target.value)}
          required
          className={input}
        >
          <option value="" disabled>
            Choose the model that will answer…
          </option>
          {baseModels.map((m) => (
            <option key={m.id} value={m.id}>
              {m.name} · {m.provider_name}
            </option>
          ))}
          {form.base_model_id && !baseModels.some((m) => m.id === form.base_model_id) && (
            <option value={form.base_model_id}>
              {form.base_model_id} (not available right now)
            </option>
          )}
        </select>
      </div>
      <div>
        <label htmlFor="cm-prompt" className={label}>
          Instructions
        </label>
        <textarea
          id="cm-prompt"
          value={form.system_prompt}
          onChange={(e) => set('system_prompt', e.target.value)}
          rows={6}
          maxLength={20000}
          placeholder="How should it behave? e.g. “You are Acme’s HR assistant. Answer from the handbook and cite it. Be friendly and concise.”"
          className={input}
        />
      </div>
      {ownKnowledge && (
        <fieldset>
          <legend className={label}>Knowledge</legend>
          {collections.data?.length === 0 && (
            <p className="text-sm text-zinc-500">
              No knowledge bases yet. Create one on the Knowledge page.
            </p>
          )}
          <div className="flex flex-wrap gap-2">
            {collections.data?.map((c) => {
              const on = form.knowledge_ids.includes(c.id)
              return (
                <label
                  key={c.id}
                  className={`flex cursor-pointer items-center gap-1.5 rounded-full border px-3 py-1 text-sm ${
                    on
                      ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-950'
                      : 'border-zinc-300 dark:border-zinc-700'
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={on}
                    onChange={() =>
                      set(
                        'knowledge_ids',
                        on
                          ? form.knowledge_ids.filter((i) => i !== c.id)
                          : [...form.knowledge_ids, c.id],
                      )
                    }
                    className="accent-indigo-600"
                  />
                  📚 {c.name}
                </label>
              )
            })}
          </div>
          <p className="mt-1 text-xs text-zinc-500">
            Searched automatically on every message; answers cite them.
          </p>
        </fieldset>
      )}
      {me.data?.role === 'admin' && (
        <fieldset>
          <legend className={label}>Who can use it</legend>
          <div className="flex gap-4 text-sm">
            <label className="flex items-center gap-1.5">
              <input
                type="radio"
                checked={form.visibility === 'private'}
                onChange={() => set('visibility', 'private')}
                className="accent-indigo-600"
              />
              Only me
            </label>
            <label className="flex items-center gap-1.5">
              <input
                type="radio"
                checked={form.visibility === 'public'}
                onChange={() => set('visibility', 'public')}
                className="accent-indigo-600"
              />
              Everyone
            </label>
          </div>
        </fieldset>
      )}
      {save.error && <p className="text-sm text-red-500">{errorMessage(save.error)}</p>}
      <div className="flex justify-end gap-2 border-t border-zinc-200 pt-4 dark:border-zinc-800">
        <button type="button" className={button} onClick={onDone}>
          Cancel
        </button>
        <button
          type="submit"
          disabled={save.isPending}
          className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
        >
          {model ? 'Save' : 'Create'}
        </button>
      </div>
    </form>
  )
}

export default function ModelsPage() {
  useDocumentTitle('Models')
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const customModels = useQuery({ queryKey: key, queryFn: listCustomModels })
  const remove = useMutation({
    mutationFn: deleteCustomModel,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: key })
      queryClient.invalidateQueries({ queryKey: ['models'] })
    },
  })
  const me = useMe()
  const [editing, setEditing] = useState<'new' | string | null>(null)
  const [confirming, setConfirming] = useState<string | null>(null)

  const startChat = (modelId: string) => {
    try {
      localStorage.setItem('webui.selectedModel', modelId)
    } catch {
      // storage unavailable; the menu just won't preselect it
    }
    // The chat page reads the remembered model when it opens.
    navigate('/')
  }

  return (
    <div className="flex h-full flex-col">
      <PageHeader title="Models" />
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-3xl space-y-4 px-4 py-6">
          <div className="flex items-start justify-between gap-2">
            <div>
              <h2 className="text-lg font-semibold">Custom models</h2>
              <p className="text-sm text-zinc-500">
                Saved assistants: a base model with your instructions and knowledge. They appear at
                the top of the model menu.
              </p>
            </div>
            {editing !== 'new' && (
              <button
                type="button"
                onClick={() => setEditing('new')}
                className="flex shrink-0 items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-2 text-sm font-medium text-white hover:bg-indigo-500"
              >
                <PlusIcon /> New
              </button>
            )}
          </div>
          {editing === 'new' && <Editor onDone={() => setEditing(null)} />}
          {customModels.isLoading && <p className="text-sm text-zinc-500">Loading…</p>}
          {customModels.isError && (
            <p className="text-sm text-red-500">{errorMessage(customModels.error)}</p>
          )}
          {customModels.isSuccess && customModels.data.length === 0 && editing !== 'new' && (
            <div className="rounded-xl border border-dashed border-zinc-300 px-4 py-10 text-center text-sm text-zinc-500 dark:border-zinc-700">
              No custom models yet. Create one, e.g. a “Python tutor” or an “HR helper” that answers
              from your handbook.
            </div>
          )}
          <ul className="space-y-3">
            {customModels.data?.map((m) =>
              editing === m.id ? (
                <li key={m.id}>
                  <Editor model={m} onDone={() => setEditing(null)} />
                </li>
              ) : (
                <li
                  key={m.id}
                  className="rounded-xl border border-zinc-200 p-4 dark:border-zinc-800"
                >
                  <div className="flex items-start gap-3">
                    <span className="text-2xl" aria-hidden="true">
                      {m.emoji}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="flex flex-wrap items-center gap-2 font-medium">
                        {m.name}
                        {m.visibility === 'public' && (
                          <span className="rounded-full bg-indigo-100 px-2 py-0.5 text-xs text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300">
                            Everyone
                          </span>
                        )}
                        {!m.is_owner && (
                          <span className="text-xs text-zinc-500">shared by an admin</span>
                        )}
                      </p>
                      {m.description && <p className="text-sm text-zinc-500">{m.description}</p>}
                      <p className="mt-1 text-xs text-zinc-500">
                        Based on <span className="font-mono">{m.base_model_id}</span>
                        {m.knowledge.length > 0 &&
                          ` · 📚 ${m.knowledge.map((k) => k.name).join(', ')}`}
                      </p>
                    </div>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <button
                      type="button"
                      className="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-500"
                      onClick={() => startChat(m.model_id)}
                    >
                      Chat
                    </button>
                    {(m.is_owner || me.data?.role === 'admin') && (
                      <>
                        <button type="button" className={button} onClick={() => setEditing(m.id)}>
                          Edit
                        </button>
                        {confirming === m.id ? (
                          <button
                            type="button"
                            className="rounded-lg bg-red-600 px-3 py-1.5 text-sm text-white hover:bg-red-500"
                            onClick={() => remove.mutate(m.id)}
                          >
                            Confirm delete
                          </button>
                        ) : (
                          <button
                            type="button"
                            className={`${button} text-red-600 dark:text-red-400`}
                            onClick={() => setConfirming(m.id)}
                          >
                            Delete
                          </button>
                        )}
                      </>
                    )}
                  </div>
                </li>
              ),
            )}
          </ul>
        </div>
      </div>
    </div>
  )
}
