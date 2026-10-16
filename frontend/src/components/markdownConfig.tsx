import type { Components } from 'react-markdown'
import { CodeBlock } from './CodeBlock'

// Links may break anywhere: a long URL is one unbreakable "word" and would
// otherwise push past its container (e.g. into the next side-by-side column).
export const PROSE =
  'prose prose-zinc max-w-none break-words dark:prose-invert prose-pre:p-0 prose-code:before:content-none prose-code:after:content-none prose-a:[overflow-wrap:anywhere]'

export const markdownComponents: Components = {
  pre: CodeBlock,
  a: ({ ...props }) => <a {...props} target="_blank" rel="noopener noreferrer" />,
  // A table wider than its space scrolls sideways inside its own box.
  table: ({ ...props }) => (
    <div className="my-4 overflow-x-auto">
      <table {...props} className="my-0" />
    </div>
  ),
}
