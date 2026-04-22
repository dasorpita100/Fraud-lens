/**
 * Groq OpenAI-compatible Chat Completions API.
 * https://console.groq.com/keys
 *
 * Supports multiple API keys and multiple models: if one model hits RPM/daily limits,
 * the client tries the next model (then the next key, if configured).
 */

const GROQ_CHAT_URL = 'https://api.groq.com/openai/v1/chat/completions';

/** Default chain after GROQ_MODEL — favor models with higher daily request caps when primary is exhausted. */
const DEFAULT_MODEL_FALLBACKS = [
  'llama-3.1-8b-instant',
  'allam-2-7b',
  'qwen/qwen3-32b',
  'meta-llama/llama-4-scout-17b-16e-instruct',
  'openai/gpt-oss-20b',
];

function getGroqApiKeys() {
  const keys = [];
  const single = (process.env.GROQ_API_KEY || '').trim();
  if (single) keys.push(single);
  const multi = (process.env.GROQ_API_KEYS || '').trim();
  multi.split(',').forEach((k) => {
    k = k.trim();
    if (k && !keys.includes(k)) keys.push(k);
  });
  return keys;
}

function defaultGroqModel() {
  return (process.env.GROQ_MODEL || 'llama-3.3-70b-versatile').trim();
}

/**
 * Ordered list of model ids to try (primary first, then fallbacks).
 * - GROQ_MODELS=comma-separated → use exactly this list (highest priority).
 * - Else GROQ_MODEL plus optional GROQ_MODEL_FALLBACKS, else DEFAULT_MODEL_FALLBACKS.
 */
function getGroqModelList() {
  const csv = (process.env.GROQ_MODELS || '').trim();
  if (csv) {
    return csv.split(',').map((s) => s.trim()).filter(Boolean);
  }
  const primary = defaultGroqModel();
  const models = [primary];
  const extra = (process.env.GROQ_MODEL_FALLBACKS || '').trim();
  if (extra) {
    extra.split(',').forEach((m) => {
      m = m.trim();
      if (m && !models.includes(m)) models.push(m);
    });
  } else {
    for (const m of DEFAULT_MODEL_FALLBACKS) {
      if (!models.includes(m)) models.push(m);
    }
  }
  return models;
}

function groqErrorWithMeta(status, message, data) {
  const err = new Error(message);
  err.status = status;
  err.groqBody = data;
  return err;
}

/**
 * True if trying another model (or key) might help.
 */
function shouldTryAlternateGroqModel(err) {
  const status = err?.status;
  const m = String(err?.message || '').toLowerCase();
  if (status === 429 || status === 408) return true;
  if (status === 503 || status === 502 || status === 504) return true;
  if (status === 400 && (m.includes('model') || m.includes('does not exist'))) return true;
  if (
    m.includes('rate limit') ||
    m.includes('too many requests') ||
    m.includes('quota') ||
    m.includes('capacity') ||
    m.includes('overloaded') ||
    m.includes('try again') ||
    m.includes('limit exceeded')
  ) {
    return true;
  }
  // Wrapped errors (e.g. fetch) use status 0 — try another model unless misconfiguration
  if (status === 0 && !m.includes('not configured')) return true;
  return false;
}

function shouldSkipRemainingModelsForKey(err) {
  const status = err?.status;
  if (status === 401 || status === 403) return true;
  return false;
}

/**
 * @param {string} prompt - user message content
 * @param {{ apiKey?: string, model?: string, maxTokens?: number, temperature?: number }} [opts]
 * @returns {Promise<string>} assistant text
 */
async function callGroqChat(prompt, opts = {}) {
  const apiKey = opts.apiKey || getGroqApiKeys()[0];
  if (!apiKey) {
    throw groqErrorWithMeta(0, 'GROQ_API_KEY not configured');
  }
  const model = opts.model || defaultGroqModel();
  const maxTokens = opts.maxTokens ?? 1024;
  const temperature = opts.temperature ?? 0.3;

  const ac = new AbortController();
  const t = setTimeout(() => ac.abort(), 60000);

  try {
    const res = await fetch(GROQ_CHAT_URL, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${apiKey}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        model,
        messages: [{ role: 'user', content: prompt }],
        max_tokens: maxTokens,
        temperature,
      }),
      signal: ac.signal,
    });

    const raw = await res.text();
    let data;
    try {
      data = JSON.parse(raw);
    } catch (_) {
      throw groqErrorWithMeta(res.status, `Groq invalid JSON (${res.status}): ${raw.slice(0, 200)}`);
    }

    if (!res.ok) {
      const msg = data?.error?.message || raw.slice(0, 300);
      throw groqErrorWithMeta(res.status, `Groq ${res.status}: ${msg}`, data);
    }

    const text = data?.choices?.[0]?.message?.content;
    if (!text || !String(text).trim()) {
      throw groqErrorWithMeta(res.status || 0, 'Empty Groq response', data);
    }
    return String(text).trim();
  } catch (e) {
    if (e.name === 'AbortError') {
      throw groqErrorWithMeta(408, 'Groq request timed out');
    }
    if (e.status !== undefined) throw e;
    throw groqErrorWithMeta(0, e?.message || String(e));
  } finally {
    clearTimeout(t);
  }
}

/**
 * Try each API key; for each key, try each model until one succeeds.
 * On rate limits / quota-style errors, advances to the next model automatically.
 * @param {string} prompt
 * @param {{ model?: string, maxTokens?: number, temperature?: number }} [opts]
 * @returns {Promise<string|null>}
 */
async function tryGroqChatWithKeys(prompt, opts = {}) {
  const keys = getGroqApiKeys();
  if (!keys.length) return null;

  const models = opts.model ? [opts.model] : getGroqModelList();
  let lastErr = null;

  for (const key of keys) {
    for (let i = 0; i < models.length; i++) {
      const model = models[i];
      try {
        const out = await callGroqChat(prompt, { ...opts, apiKey: key, model });
        if (out) {
          if (i > 0) {
            console.info(`Groq: succeeded with fallback model "${model}" (${i} earlier model(s) failed).`);
          }
          return out;
        }
      } catch (e) {
        lastErr = e;
        console.warn(`Groq model "${model}" failed:`, e?.message || e);
        if (shouldSkipRemainingModelsForKey(e)) {
          break;
        }
        if (!shouldTryAlternateGroqModel(e)) {
          break;
        }
      }
    }
  }

  if (lastErr) console.warn('All Groq models/keys failed:', lastErr?.message || lastErr);
  return null;
}

module.exports = {
  getGroqApiKeys,
  getGroqModelList,
  defaultGroqModel,
  callGroqChat,
  tryGroqChatWithKeys,
  GROQ_CHAT_URL,
};
