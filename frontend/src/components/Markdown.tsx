import { isValidElement, memo, useRef, useState, type ComponentPropsWithoutRef } from 'react'
import ReactMarkdown from 'react-markdown'
import rehypeHighlight from 'rehype-highlight'
import remarkGfm from 'remark-gfm'
import { CheckIcon, CopyIcon } from './icons'

function CodeBlock({ children, ...props }: ComponentPropsWithoutRef<'pre'>) {
  const ref = useRef<HTMLPreElement>(null)
  const [copied, setCopied] = useState(false)

  const codeClass = isValidElement<{ className?: string }>(children)
    ? (children.props.className ?? '')
    : ''
  const language = codeClass.match(/language-([\w-]+)/)?.[1]

  const copy = async () => {
    const text = ref.current?.querySelector('code')?.textContent ?? ''
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      // clipboard blocked (e.g. insecure context); nothing useful to do
    }
  }

  return (
    <div className="not-prose my-3 overflow-hidden rounded-lg border border-zinc-200 dark:border-zinc-800">
      <div className="flex items-center justify-between bg-zinc-100 px-3 py-1 text-xs text-zinc-500 dark:bg-zinc-900">
        <span>{language ?? 'code'}</span>
        <button
          type="button"
          onClick={copy}
          className="flex items-center gap-1 rounded px-1.5 py-0.5 hover:bg-zinc-200 hover:text-zinc-900 dark:hover:bg-zinc-800 dark:hover:text-zinc-100"
        >
          {copied ? <CheckIcon width={14} height={14} /> : <CopyIcon width={14} height={14} />}
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>
      <pre
        ref={ref}
        {...props}
        className="overflow-x-auto bg-zinc-50 p-3 text-[13px] leading-relaxed dark:bg-zinc-950"
      >
        {children}
      </pre>
    </div>
  )
}

function Markdown({ content }: { content: string }) {
  return (
    <div className="prose prose-zinc max-w-none break-words dark:prose-invert prose-pre:p-0 prose-code:before:content-none prose-code:after:content-none">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[[rehypeHighlight, { detect: true, ignoreMissing: true }]]}
        components={{
          pre: CodeBlock,
          a: ({ ...props }) => <a {...props} target="_blank" rel="noopener noreferrer" />,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
}

export default memo(Markdown)
