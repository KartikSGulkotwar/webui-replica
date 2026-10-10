import { useLayoutEffect, useRef, type ReactNode } from 'react'

interface Props {
  children: ReactNode
  /** Changes whenever content grows (e.g. message count + streamed length). */
  contentKey: string | number
}

/** Scrolling message area that follows new content unless the user scrolled up. */
export default function ChatWindow({ children, contentKey }: Props) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const stickRef = useRef(true)

  const onScroll = () => {
    const el = scrollRef.current
    if (!el) return
    stickRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80
  }

  useLayoutEffect(() => {
    const el = scrollRef.current
    if (el && stickRef.current) el.scrollTop = el.scrollHeight
  }, [contentKey])

  return (
    <div ref={scrollRef} onScroll={onScroll} className="flex-1 overflow-y-auto">
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-4 py-6">{children}</div>
    </div>
  )
}
