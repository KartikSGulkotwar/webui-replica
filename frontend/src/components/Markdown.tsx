import { lazy, memo, Suspense } from 'react'
import ReactMarkdown from 'react-markdown'
import rehypeHighlight from 'rehype-highlight'
import remarkGfm from 'remark-gfm'
import { hasMath } from '../lib/math'
import { markdownComponents, PROSE } from './markdownConfig'

// KaTeX is large, so it only loads for messages that contain math.
const MathMarkdown = lazy(() => import('./MathMarkdown'))

function PlainMarkdown({ content }: { content: string }) {
  return (
    <div className={PROSE}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[[rehypeHighlight, { detect: true, ignoreMissing: true }]]}
        components={markdownComponents}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
}

function Markdown({ content }: { content: string }) {
  if (!hasMath(content)) return <PlainMarkdown content={content} />
  return (
    <Suspense fallback={<PlainMarkdown content={content} />}>
      <MathMarkdown content={content} />
    </Suspense>
  )
}

export default memo(Markdown)
