import { Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import ChatPage from './pages/ChatPage'
import SettingsPage from './pages/SettingsPage'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        {/* Both routes render the same ChatPage instance, so a stream started on "/"
            keeps running when the URL changes to the new conversation. */}
        <Route path="/" element={<ChatPage />} />
        <Route path="/c/:id" element={<ChatPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="*" element={<ChatPage />} />
      </Route>
    </Routes>
  )
}
