/* Unified player adapters.  They expose one small, provider-neutral API. */
export class HTML5MediaAdapter {
  constructor(element) { this.element = element; }
  play() { return this.element.play(); }
  pause() { this.element.pause(); }
  seek(seconds) { this.element.currentTime = Math.max(0, Number(seconds) || 0); }
  currentTime() { return Number(this.element.currentTime || 0); }
  duration() { return Number(this.element.duration || 0); }
  progress() { const d = this.duration(); return d ? this.currentTime() / d : 0; }
}

export class YouTubeMediaAdapter {
  constructor(player) { this.player = player; }
  play() { return this.player.playVideo(); }
  pause() { return this.player.pauseVideo(); }
  seek(seconds) { return this.player.seekTo(Math.max(0, Number(seconds) || 0), true); }
  currentTime() { return Number(this.player.getCurrentTime() || 0); }
  duration() { return Number(this.player.getDuration() || 0); }
  progress() { const d = this.duration(); return d ? this.currentTime() / d : 0; }
}

// Ten-second coverage buckets deliberately make a jump to the last second
// insufficient to mark a material complete.
export class MediaProgressTracker {
  constructor(adapter) { this.adapter = adapter; this.buckets = new Set(); }
  sample() { this.buckets.add(Math.floor(this.adapter.currentTime() / 10)); }
  payload() { return { lastPositionSeconds: this.adapter.currentTime(), duration: this.adapter.duration(), watchedBuckets: [...this.buckets] }; }
}
