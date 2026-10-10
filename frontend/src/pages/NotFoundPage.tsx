import { Link } from 'react-router-dom'

export default function NotFoundPage() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 p-6 text-center">
      <h1 className="text-xl font-semibold">Page not found</h1>
      <p className="text-sm text-zinc-500">There’s nothing at this address.</p>
      <Link to="/" className="text-sm text-indigo-500 hover:underline">
        Start a new chat
      </Link>
    </div>
  )
}
