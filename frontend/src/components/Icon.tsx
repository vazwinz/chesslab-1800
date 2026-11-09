const PATHS: Record<string, string> = {
  home: "M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z",
  train: "M4 4h16v16H4zM4 12h16M12 4v16M8 8h.01M16 16h.01",
  games: "M7 4h10l3 4-8 12L4 8zM4 8h16M10 4l-2 4 4 12 4-12-2-4",
  analysis: "M10.5 18a7.5 7.5 0 1 1 0-15 7.5 7.5 0 0 1 0 15zM16 16l5 5M7.5 10.5h6M10.5 7.5v6",
  book: "M4 5a2 2 0 0 1 2-2h13v15H6a2 2 0 0 0-2 2zM4 20a2 2 0 0 0 2 1h13",
  king: "M12 2v4M10 4h4M7 21h10M8 21l-1-6h10l-1 6M7 15c-2-3 0-7 5-7s7 4 5 7",
  plan: "M4 6h16v14H4zM4 10h16M8 3v4M16 3v4M8 14h3M8 17h6",
  chart: "M4 20V4M4 20h16M8 16l4-5 3 3 5-7",
  guide: "M12 21a9 9 0 1 1 0-18 9 9 0 0 1 0 18zM9.5 9a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6V14M12 17h.01",
  settings: "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z",
  sun: "M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10zM12 1v2M12 21v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M1 12h2M21 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4",
  moon: "M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z",
  menu: "M3 6h18M3 12h18M3 18h18",
  x: "M6 6l12 12M18 6 6 18",
  flip: "M7 4v16M7 20l-3-3M7 20l3-3M17 20V4M17 4l-3 3M17 4l3 3",
  back: "M15 18l-6-6 6-6",
  forward: "M9 18l6-6-6-6",
  first: "M17 18l-6-6 6-6M7 6v12",
  last: "M7 18l6-6-6-6M17 6v12",
  sound: "M11 5 6 9H2v6h4l5 4zM15.5 8.5a5 5 0 0 1 0 7M19 5a10 10 0 0 1 0 14",
  mute: "M11 5 6 9H2v6h4l5 4zM23 9l-6 6M17 9l6 6",
  download: "M12 3v12M7 10l5 5 5-5M5 21h14",
  bolt: "M13 2 3 14h9l-1 8 10-12h-9z",
  play: "M12 3.4a2.6 2.6 0 1 1 0 5.2 2.6 2.6 0 0 1 0-5.2zM9 10h6M10.2 10c0 3-1.2 5-2.7 6.5h9c-1.5-1.5-2.7-3.5-2.7-6.5M6.3 20.5h11.4l-.6-4H6.9z",
};

export default function Icon({ name, size = 20, className = "" }: { name: keyof typeof PATHS | string; size?: number;
  className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8}
      strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden>
      <path d={PATHS[name] ?? ""} />
    </svg>
  );
}
