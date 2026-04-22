/**
 * Explanations when Gemini is unavailable: deterministic text aligned with ML verdict/score/reasons,
 * optional Hugging Face Inference API, optional URLhaus URL reputation (public, no key).
 */

const HF_MODEL =
  process.env.HUGGINGFACE_EXPLAIN_MODEL || 'mistralai/Mistral-7B-Instruct-v0.2';

function isRiskyVerdict(verdict) {
  return ['Phishing', 'Scam', 'Fraud', 'Suspicious'].includes(verdict);
}

/**
 * First http(s) URL in text, or null.
 */
function extractFirstUrl(text) {
  if (!text || typeof text !== 'string') return null;
  const m = text.match(/https?:\/\/[^\s<>"']+/i);
  return m ? m[0].slice(0, 2048) : null;
}

/**
 * URLhaus public API — no API key. Returns a short note if URL is known badware.
 * https://urlhaus-api.abuse.ch/
 */
async function urlhausNoteForContent(contentPreview) {
  const url = extractFirstUrl(contentPreview);
  if (!url) return '';
  try {
    const ac = new AbortController();
    const t = setTimeout(() => ac.abort(), 8000);
    const res = await fetch('https://urlhaus-api.abuse.ch/v1/url/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({ url }),
      signal: ac.signal,
    });
    clearTimeout(t);
    const data = await res.json().catch(() => ({}));
    if (data.query_status === 'ok' && data.threat) {
      const tags = Array.isArray(data.tags) ? data.tags.slice(0, 3).join(', ') : String(data.threat);
      return ` Independent check: URLhaus reports this link (${String(data.threat).slice(0, 80)}; tags: ${tags}). Treat it as dangerous.`;
    }
  } catch (_) {
    /* ignore */
  }
  return '';
}

function buildDeterministicExplanation(scanType, verdict, score, reasons, contentPreview = '') {
  const reasonText =
    Array.isArray(reasons) && reasons.length
      ? reasons.join(' ')
      : 'No specific indicators were listed beyond the model score.';
  const s = Math.min(100, Math.max(0, Number(score) || 0));
  const st = (scanType || 'email').toLowerCase();
  const risky = isRiskyVerdict(verdict);

  if (st === 'email') {
    if (risky) {
      return (
        `Our fraud-detection model classified this message as ${verdict} with a risk score of ${s} out of 100. ` +
        `Signals it used include: ${reasonText}. ` +
        `Do not click links or reply with personal data until you have verified the sender through an official channel. ` +
        `If something feels urgent or threatening, slow down—that is a common phishing tactic.`
      );
    }
    return (
      `Our model classified this email as ${verdict} with a risk score of ${s} out of 100. ` +
      `Observed signals: ${reasonText}. ` +
      `That suggests no strong phishing pattern in this sample, but you should still verify unexpected requests through trusted contact points.`
    );
  }

  if (st === 'sms') {
    if (risky) {
      return (
        `Our model classified this SMS as ${verdict} with a risk score of ${s} out of 100. ` +
        `Signals include: ${reasonText}. ` +
        `Do not share OTPs or passwords, do not follow payment links from unknown senders, and block or report the number if you were not expecting this message.`
      );
    }
    return (
      `Our model classified this SMS as ${verdict} with a risk score of ${s} out of 100. ` +
      `Signals: ${reasonText}. ` +
      `It does not match common scam templates strongly, but stay cautious with any unexpected financial or login requests.`
    );
  }

  // UPI
  if (risky) {
    return (
      `Our model rated this transaction as ${verdict} with a risk score of ${s} out of 100. ` +
      `Factors considered: ${reasonText}. ` +
      `Before paying, confirm the recipient’s identity on a trusted channel, especially for large or first-time transfers. ` +
      `If anything about the UPI ID or timing feels off, pause and verify with your bank or the intended payee.`
    );
  }
  return (
    `Our model rated this transaction as ${verdict} with a risk score of ${s} out of 100. ` +
    `Signals: ${reasonText}. ` +
    `That indicates lower modeled risk, but always double-check recipient details for important payments.`
  );
}

/**
 * Async wrapper: deterministic paragraph + optional URLhaus sentence.
 */
async function buildDeterministicExplanationAsync(
  scanType,
  verdict,
  score,
  reasons,
  contentPreview,
) {
  let base = buildDeterministicExplanation(scanType, verdict, score, reasons, contentPreview);
  if ((scanType || '').toLowerCase() === 'upi') {
    return base;
  }
  const extra = await urlhausNoteForContent(contentPreview);
  return base + extra;
}

/**
 * Hugging Face Inference API (optional HUGGINGFACE_API_TOKEN). Uses chat-style prompt.
 */
async function tryHuggingFaceExplanation(prompt) {
  const token = (process.env.HUGGINGFACE_API_TOKEN || '').trim();
  if (!token) return null;

  const url = `https://api-inference.huggingface.co/models/${HF_MODEL}`;
  const wrapped = `<s>[INST] ${prompt.replace(/\s+/g, ' ').trim()} [/INST]`;

  const ac = new AbortController();
  const timeout = setTimeout(() => ac.abort(), 45000);

  try {
    const res = await fetch(url, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        inputs: wrapped,
        parameters: { max_new_tokens: 320, return_full_text: false },
      }),
      signal: ac.signal,
    });

    if (res.status === 503) {
      // Model loading — HF returns this often; treat as soft fail
      return null;
    }

    const data = await res.json().catch(() => null);
    if (!data) return null;

    let text = null;
    if (Array.isArray(data) && data[0] && data[0].generated_text) {
      text = String(data[0].generated_text).trim();
    } else if (data.generated_text) {
      text = String(data.generated_text).trim();
    } else if (typeof data === 'string') {
      text = data.trim();
    }

    if (text && text.length > 20) return text;
    return null;
  } catch (_) {
    return null;
  } finally {
    clearTimeout(timeout);
  }
}

module.exports = {
  buildDeterministicExplanation,
  buildDeterministicExplanationAsync,
  tryHuggingFaceExplanation,
  urlhausNoteForContent,
  extractFirstUrl,
  isRiskyVerdict,
};
