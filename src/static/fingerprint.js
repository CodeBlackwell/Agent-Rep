/**
 * Lightweight browser fingerprint — generates a stable hash from
 * browser properties that don't change between page loads.
 *
 * NOT a tracking tool — used solely for per-visitor rate limiting
 * to prevent API abuse. No cookies, no localStorage persistence.
 */
(function () {
  async function generateFingerprint() {
    const components = [
      navigator.language,
      navigator.languages ? navigator.languages.join(',') : '',
      screen.width + 'x' + screen.height,
      screen.colorDepth,
      new Date().getTimezoneOffset(),
      navigator.hardwareConcurrency || '',
      navigator.maxTouchPoints || 0,
      navigator.platform || '',
    ];

    // Canvas fingerprint — renders text and extracts a hash
    try {
      const canvas = document.createElement('canvas');
      const ctx = canvas.getContext('2d');
      canvas.width = 200;
      canvas.height = 50;
      ctx.textBaseline = 'top';
      ctx.font = '14px Arial';
      ctx.fillStyle = '#f60';
      ctx.fillRect(50, 0, 100, 50);
      ctx.fillStyle = '#069';
      ctx.fillText('ShowMeOff:fp', 2, 15);
      ctx.fillStyle = 'rgba(102, 204, 0, 0.7)';
      ctx.fillText('ShowMeOff:fp', 4, 17);
      components.push(canvas.toDataURL().slice(-50));
    } catch (e) {
      components.push('no-canvas');
    }

    // Hash the components into a short hex string
    const raw = components.join('|');
    const encoded = new TextEncoder().encode(raw);
    const hashBuffer = await crypto.subtle.digest('SHA-256', encoded);
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    return hashArray.map(b => b.toString(16).padStart(2, '0')).join('').slice(0, 16);
  }

  generateFingerprint().then(fp => {
    window.__fp = fp;
  }).catch(() => {
    window.__fp = 'unknown';
  });
})();
