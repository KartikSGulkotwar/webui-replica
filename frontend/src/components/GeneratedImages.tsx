import { imageUrl } from '../api/images'
import type { ImageRef } from '../types/api'
import { DownloadIcon } from './icons'

/** Images made for a reply; click to open full size. `creating` shows a placeholder. */
export default function GeneratedImages({
  images,
  creating,
}: {
  images: ImageRef[]
  creating?: boolean
}) {
  if (!images.length && !creating) return null
  return (
    <div className="flex flex-wrap gap-2" aria-label="Generated images">
      {images.map((image) => (
        <figure key={image.id} className="group relative w-full max-w-sm">
          <a href={imageUrl(image.id)} target="_blank" rel="noreferrer" title="Open full size">
            <img
              src={imageUrl(image.id)}
              alt={image.prompt}
              loading="lazy"
              className="aspect-square w-full rounded-xl border border-zinc-200 bg-zinc-100 object-cover dark:border-zinc-800 dark:bg-zinc-900"
            />
          </a>
          <a
            href={imageUrl(image.id)}
            download={`image-${image.id.slice(0, 8)}`}
            className="absolute right-2 top-2 rounded-lg bg-black/60 p-1.5 text-white opacity-0 transition-opacity hover:bg-black/80 focus:opacity-100 group-hover:opacity-100"
            aria-label="Download image"
            title="Download"
          >
            <DownloadIcon />
          </a>
          <figcaption className="sr-only">{image.prompt}</figcaption>
        </figure>
      ))}
      {creating && (
        <div
          className="flex aspect-square w-full max-w-sm animate-pulse items-center justify-center rounded-xl border border-zinc-200 bg-zinc-100 text-sm text-zinc-500 dark:border-zinc-800 dark:bg-zinc-900"
          role="status"
        >
          🎨 Creating image…
        </div>
      )}
    </div>
  )
}
