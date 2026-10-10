import { Route, Routes } from 'react-router-dom'
import ChatPage from './pages/ChatPage'

export default function App() {
  return (
    <div className="h-full bg-white text-zinc-900 dark:bg-zinc-950 dark:text-zinc-100">
      <Routes>
        <Route path="/" element={<ChatPage />} />
        <Route path="*" element={<ChatPage />} />
      </Routes>
    </div>
  )
}
