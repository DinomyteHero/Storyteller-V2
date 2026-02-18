<script lang="ts">
  /**
   * OpeningCrawl.svelte — Star Wars-style scrolling opening crawl.
   *
   * Shown once per campaign (gated by localStorage["crawl_shown_{campaign_id}"]).
   * The parent passes `crawlText` and `campaignId`. The `ondone` callback fires
   * when the animation ends or the user skips it.
   */
  interface Props {
    crawlText: string;
    campaignId: string;
    title?: string;
    ondone?: () => void;
  }

  let { crawlText, campaignId, title = 'Episode I', ondone }: Props = $props();

  function skip() {
    markShown();
    ondone?.();
  }

  function markShown() {
    try {
      localStorage.setItem(`crawl_shown_${campaignId}`, '1');
    } catch {
      // localStorage may be unavailable in some contexts
    }
  }

  function handleAnimationEnd() {
    markShown();
    // Brief pause after animation ends before calling ondone
    setTimeout(() => ondone?.(), 1200);
  }
</script>

<div class="crawl-container" role="presentation">
  <!-- Skip button -->
  <button class="skip-btn" onclick={skip} type="button">Skip ▶</button>

  <div class="crawl-stage">
    <div class="crawl-content" onanimationend={handleAnimationEnd}>
      <div class="episode-label">{title}</div>
      <div class="crawl-text">{crawlText}</div>
    </div>
  </div>
</div>

<style>
  .crawl-container {
    position: fixed;
    inset: 0;
    background: #000;
    z-index: 1000;
    display: flex;
    align-items: center;
    justify-content: center;
    overflow: hidden;
  }

  .skip-btn {
    position: absolute;
    top: 1.5rem;
    right: 1.5rem;
    background: transparent;
    border: 1px solid rgba(255, 230, 120, 0.3);
    color: rgba(255, 230, 120, 0.6);
    padding: 0.4rem 1rem;
    border-radius: 4px;
    cursor: pointer;
    font-size: 0.8rem;
    letter-spacing: 0.1em;
    z-index: 10;
    transition: border-color 0.15s, color 0.15s;
  }

  .skip-btn:hover {
    border-color: rgba(255, 230, 120, 0.7);
    color: rgba(255, 230, 120, 0.9);
  }

  .crawl-stage {
    width: 100%;
    height: 100%;
    perspective: 300px;
    overflow: hidden;
    display: flex;
    align-items: flex-end;
    justify-content: center;
  }

  .crawl-content {
    width: min(600px, 90vw);
    padding: 0 1rem;
    text-align: center;
    transform-origin: 50% 100%;
    animation: crawl 24s linear forwards;
  }

  @keyframes crawl {
    from {
      transform: rotateX(30deg) translateY(100vh);
      opacity: 0;
    }
    5% {
      opacity: 1;
    }
    90% {
      opacity: 1;
    }
    to {
      transform: rotateX(30deg) translateY(-200%);
      opacity: 0;
    }
  }

  .episode-label {
    font-size: 1.2rem;
    letter-spacing: 0.3em;
    text-transform: uppercase;
    color: #ffe878;
    margin-bottom: 2rem;
    opacity: 0.8;
  }

  .crawl-text {
    font-size: 1.3rem;
    line-height: 1.9;
    color: #ffe878;
    font-family: 'Georgia', serif;
    text-shadow: 0 0 20px rgba(255, 232, 120, 0.4);
    white-space: pre-wrap;
    word-break: break-word;
  }
</style>
