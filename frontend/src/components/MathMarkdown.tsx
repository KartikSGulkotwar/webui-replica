import ReactMarkdown from 'react-markdown'
import rehypeHighlight from 'rehype-highlight'
import rehypeKatex from 'rehype-katex'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import 'katex/dist/katex.min.css'
import { normalizeMath } from '../lib/math'
import { markdownComponents, PROSE } from './markdownConfig'

/** Markdown with LaTeX. Loaded only for messages that contain math. */
export default function MathMarkdown({ content }: { content: string }) {
  return (
    <div className={PROSE}>
      <ReactMarkdown
        // singleDollarTextMath off: "$5 and $10" is money, not math. Inline math
        // uses $$…$$ (normalizeMath converts the \( \) form models usually write).
        remarkPlugins={[remarkGfm, [remarkMath, { singleDollarTextMath: false }]]}
        rehypePlugins={[
          [rehypeKatex, { throwOnError: false, strict: false }],
          [rehypeHighlight, { detect: true, ignoreMissing: true }],
        ]}
        components={markdownComponents}
      >
        {normalizeMath(content)}
      </ReactMarkdown>
    </div>
  )
}
