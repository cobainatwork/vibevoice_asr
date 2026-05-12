const YT_URL_RE = /^https?:\/\/(www\.)?(youtube\.com\/(watch\?v=|shorts\/)|youtu\.be\/)/i;

export function isYoutubeUrl(url: string): boolean {
  return YT_URL_RE.test(url.trim());
}
