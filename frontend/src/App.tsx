import { Route, Routes } from 'react-router-dom'
import ChatPage from './pages/ChatPage'

export default function App() {
  return (
    <div className="h-full bg-white text-zinc-900 dark:bg-zinc-950 dark:text-zinc-100">
      {/* Both routes render the same ChatPage instance, so a stream started on "/"
          keeps running when the URL changes to the new conversation. */}
      <Routes>
        <Route path="/" element={<ChatPage />} />
        <Route path="/c/:id" element={<ChatPage />} />
        <Route path="*" element={<ChatPage />} />
      </Routes>
    </div>
  )
}
