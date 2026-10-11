import type { Components } from 'react-markdown'
import { CodeBlock } from './CodeBlock'

export const PROSE =
  'prose prose-zinc max-w-none break-words dark:prose-invert prose-pre:p-0 prose-code:before:content-none prose-code:after:content-none'

export const markdownComponents: Components = {
  pre: CodeBlock,
  a: ({ ...props }) => <a {...props} target="_blank" rel="noopener noreferrer" />,
}
