import { X } from "lucide-react";
import { useRef, useState } from "react";

const MIN_SCALE = 0.5;
const MAX_SCALE = 6;
const clampScale = (scale: number): number => Math.max(MIN_SCALE, Math.min(MAX_SCALE, scale));

/** Full-window viewer for a book illustration: wheel or buttons to zoom, drag to pan. */
export function ImageZoom({ image, onClose }: { image: { src: string; alt: string }; onClose: () => void }) {
  const [scale, setScale] = useState(1);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const pan = useRef<{ x: number; y: number; ox: number; oy: number } | null>(null);

  return <div className="image-zoom" role="dialog" aria-modal="true" aria-label={image.alt}
    onWheel={(event) => { event.preventDefault(); setScale((current) => clampScale(current + (event.deltaY < 0 ? 0.25 : -0.25))); }}
    onPointerMove={(event) => { if (pan.current) setOffset({ x: pan.current.ox + event.clientX - pan.current.x, y: pan.current.oy + event.clientY - pan.current.y }); }}
    onPointerUp={() => { pan.current = null; }}
    onClick={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <button className="zoom-close" aria-label="Close image zoom" onClick={onClose}><X/></button>
    <button className="zoom-reset" onClick={() => { setScale(1); setOffset({ x: 0, y: 0 }); }}>Reset</button>
    <button className="zoom-out" aria-label="Zoom out" onClick={() => setScale((current) => clampScale(current - 0.25))}>−</button>
    <button className="zoom-in" aria-label="Zoom in" onClick={() => setScale((current) => clampScale(current + 0.25))}>+</button>
    <output className="zoom-level">{Math.round(scale * 100)}%</output>
    <img src={image.src} alt={image.alt} draggable={false} style={{ transform: `translate(${offset.x}px,${offset.y}px) scale(${scale})` }}
      onPointerDown={(event) => { event.currentTarget.setPointerCapture(event.pointerId); pan.current = { x: event.clientX, y: event.clientY, ox: offset.x, oy: offset.y }; }}/>
  </div>;
}
