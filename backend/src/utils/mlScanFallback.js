/**
 * Fallback to Python FraudLens ML API when Gemini fails or is not configured.
 * Set ML_SERVICE_URL in .env (default http://127.0.0.1:5001).
 */

const ML_SERVICE_URL = (process.env.ML_SERVICE_URL || 'http://127.0.0.1:5001').replace(/\/$/, '');

async function postJson(path, body, timeoutMs = 25000) {
  const ac = new AbortController();
  const t = setTimeout(() => ac.abort(), timeoutMs);
  try {
    const res = await fetch(`${ML_SERVICE_URL}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: ac.signal,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(data.error || data.message || `ML HTTP ${res.status}`);
    }
    return data;
  } finally {
    clearTimeout(t);
  }
}

async function predictEmail(text) {
  return postJson('/predict/email', { text: text || '' });
}

async function predictSms(text) {
  return postJson('/predict/sms', { text: text || '' });
}

async function predictUpi(body) {
  return postJson('/predict/upi', body || {});
}

module.exports = {
  ML_SERVICE_URL,
  predictEmail,
  predictSms,
  predictUpi,
};
