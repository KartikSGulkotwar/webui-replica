import { useEffect } from 'react'

const APP = 'WebUI Replica'

export function useDocumentTitle(title: string | undefined) {
  useEffect(() => {
    document.title = title ? `${title} · ${APP}` : APP
  }, [title])
}
