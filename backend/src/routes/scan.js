/**
 * Scan routes: Gemini-first fraud detection; falls back to Python ML API if Gemini fails or is unset.
 * POST /api/scan/email, /api/scan/sms, /api/scan/upi
 * Body: { text } for email/sms, { text } or { amount, sender_upi, receiver_upi, ... } for upi.
 * Returns: { verdict, score, reasons, explanation, extracted_text?, parsed_fields?, source? }
 */

const express = require('express');
const { predictEmail, predictSms, predictUpi, ML_SERVICE_URL } = require('../utils/mlScanFallback');
const { buildDeterministicExplanation } = require('../utils/explanationFallbacks');
const { tryGroqChatWithKeys } = require('../utils/groqClient');

const router = express.Router();

function getApiKeys() {
  const keys = [];
  const single = (process.env.GEMINI_API_KEY || '').trim();
  if (single) keys.push(single);
  const multi = (process.env.GEMINI_API_KEYS || '').trim();
  multi.split(',').forEach((k) => {
    k = k.trim();
    if (k && !keys.includes(k)) keys.push(k);
  });
  return keys;
}

async function callGemini(apiKey, prompt) {
  const { GoogleGenerativeAI } = require('@google/generative-ai');
  const genAI = new GoogleGenerativeAI(apiKey);
  const model = genAI.getGenerativeModel({ model: 'gemini-2.5-flash' });
  const result = await model.generateContent(prompt);
  const response = result.response;
  if (!response) throw new Error('No response from Gemini');
  const cand = response.candidates && response.candidates[0];
  if (cand && cand.finishReason && cand.finishReason !== 'STOP') {
    throw new Error(`Gemini stopped: ${cand.finishReason}`);
  }
  let text = null;
  if (typeof response.text === 'function') {
    const out = response.text();
    text = typeof out?.then === 'function' ? await out : out;
  }
  text = text ? String(text).trim() : null;
  if (!text) throw new Error('Empty response from Gemini');
  return text;
}

/** Extract first JSON object from text (handles markdown code blocks and extra text). */
function parseJsonFromResponse(text) {
  if (!text) return null;
  const trimmed = text.trim();
  // Try ```json ... ``` or ``` ... ``` first
  const codeBlock = trimmed.match(/```(?:json)?\s*([\s\S]*?)```/);
  const toParse = codeBlock ? codeBlock[1].trim() : trimmed;
  // Find first { and matching }
  const start = toParse.indexOf('{');
  if (start === -1) return null;
  let depth = 0;
  let end = -1;
  for (let i = start; i < toParse.length; i++) {
    if (toParse[i] === '{') depth++;
    else if (toParse[i] === '}') {
      depth--;
      if (depth === 0) {
        end = i;
        break;
      }
    }
  }
  const jsonStr = end !== -1 ? toParse.slice(start, end + 1) : toParse.slice(start);
  try {
    return JSON.parse(jsonStr);
  } catch (_) {
    return null;
  }
}

function userFriendlyGeminiError(err) {
  const msg = (err && err.message) ? String(err.message) : '';
  if (/API_KEY|api key|invalid.*key/i.test(msg)) return 'Invalid Gemini API key. Check backend .env';
  if (/429|quota|rate limit/i.test(msg)) return 'Gemini quota exceeded. Try again later.';
  if (/403|permission|forbidden/i.test(msg)) return 'Gemini access denied. Check API key and permissions.';
  return msg || 'Gemini request failed';
}

function mlEmailResponse(text, ml) {
  const verdict = ml.verdict;
  const score = Math.min(100, Math.max(0, Number(ml.score) || 50));
  const reasons = Array.isArray(ml.reasons) ? ml.reasons : [];
  return {
    success: true,
    verdict,
    score,
    reasons,
    explanation: buildDeterministicExplanation('email', verdict, score, reasons, text),
    extracted_text: text,
    source: 'ml-fallback',
  };
}

function mlSmsResponse(text, ml) {
  const verdict = ml.verdict;
  const score = Math.min(100, Math.max(0, Number(ml.score) || 50));
  const reasons = Array.isArray(ml.reasons) ? ml.reasons : [];
  return {
    success: true,
    verdict,
    score,
    reasons,
    explanation: buildDeterministicExplanation('sms', verdict, score, reasons, text),
    extracted_text: text,
    source: 'ml-fallback',
  };
}

function mlUpiResponse(body, contentStr, ml) {
  const verdict = ml.verdict;
  const score = Math.min(100, Math.max(0, Number(ml.score) || 50));
  const reasons = Array.isArray(ml.reasons) ? ml.reasons : [];
  const extracted_text = body.text || contentStr;
  const parsed_fields =
    body.amount != null || body.receiver_upi
      ? {
          amount: body.amount,
          receiver_upi: body.receiver_upi,
          sender_upi: body.sender_upi,
          time: body.time_of_day != null ? `Hour: ${body.time_of_day}` : undefined,
          status: undefined,
        }
      : undefined;
  return {
    success: true,
    verdict,
    score,
    reasons,
    explanation: buildDeterministicExplanation('upi', verdict, score, reasons, contentStr),
    extracted_text: extracted_text || contentStr,
    parsed_fields: parsed_fields || undefined,
    source: 'ml-fallback',
  };
}

async function tryMlEmail(text) {
  const ml = await predictEmail(text);
  return mlEmailResponse(text, ml);
}

async function tryMlSms(text) {
  const ml = await predictSms(text);
  return mlSmsResponse(text, ml);
}

async function tryMlUpi(body, contentForPrompt) {
  const t = (body.text || '').trim();
  const ml = t
    ? await predictUpi({ text: t })
    : await predictUpi({
        amount: body.amount,
        sender_upi: body.sender_upi,
        receiver_upi: body.receiver_upi,
        time_of_day: body.time_of_day,
        day_of_week: body.day_of_week,
        transaction_type: body.transaction_type,
        is_new_recipient: body.is_new_recipient,
        device_changed: body.device_changed,
      });
  return mlUpiResponse(body, contentForPrompt, ml);
}

// POST /api/scan/email
router.post('/email', async (req, res) => {
  try {
    const text = (req.body?.text || '').trim();
    if (!text || text.length < 3) {
      return res.status(400).json({ success: false, message: 'text is required (min 3 characters).' });
    }
    const content = text.slice(0, 4000);
    const prompt = `You are an email phishing detector. Your verdict and explanation MUST be consistent.

RULES:
- If the email has red flags (urgent action, suspicious links, sender/domain mismatch, request for credentials, prize/refund claims), set verdict to "Phishing" and score 60-100. Your explanation must describe WHY it is phishing.
- Only set verdict to "Legitimate" if there are no such red flags; then explain why it looks safe. Do NOT say "why this looks legitimate" in the explanation text if you actually found risks—in that case use "Phishing" and explain the risks.

Respond with ONLY a valid JSON object (no markdown, no code block):
{"verdict": "Phishing" or "Legitimate", "score": number 0-100 (100 = most likely phishing), "reasons": ["reason1", "reason2", "reason3"], "explanation": "2-4 sentences that match the verdict: either why it is phishing (risks, red flags) OR why it is legitimate (no red flags)."}

Email content:
---
${content}
---`;
    const apiKeys = getApiKeys();
    let lastError = null;
    for (const key of apiKeys) {
      if (!key) continue;
      try {
        const raw = await callGemini(key, prompt);
        const parsed = parseJsonFromResponse(raw);
        const verdict = parsed && parsed.verdict ? String(parsed.verdict).trim() : '';
        if (parsed && (verdict === 'Phishing' || verdict === 'Legitimate')) {
          return res.json({
            success: true,
            verdict,
            score: Math.min(100, Math.max(0, Number(parsed.score) || 50)),
            reasons: Array.isArray(parsed.reasons) ? parsed.reasons : [],
            explanation: parsed.explanation || null,
            extracted_text: text,
            source: 'gemini',
          });
        }
        if (raw && !parsed) {
          console.warn('Scan email: Gemini response was not valid JSON. First 300 chars:', raw.slice(0, 300));
        }
      } catch (e) {
        lastError = e;
      }
    }

    const groqRaw = await tryGroqChatWithKeys(prompt, { maxTokens: 1024, temperature: 0.15 });
    if (groqRaw) {
      const parsed = parseJsonFromResponse(groqRaw);
      const verdict = parsed && parsed.verdict ? String(parsed.verdict).trim() : '';
      if (parsed && (verdict === 'Phishing' || verdict === 'Legitimate')) {
        return res.json({
          success: true,
          verdict,
          score: Math.min(100, Math.max(0, Number(parsed.score) || 50)),
          reasons: Array.isArray(parsed.reasons) ? parsed.reasons : [],
          explanation: parsed.explanation || null,
          extracted_text: text,
          source: 'groq',
        });
      }
      if (!parsed) {
        console.warn('Scan email: Groq response was not valid JSON. First 300 chars:', groqRaw.slice(0, 300));
      }
    }

    try {
      const out = await tryMlEmail(text);
      return res.json(out);
    } catch (mlErr) {
      const msg = userFriendlyGeminiError(lastError);
      console.error('Scan email failed (LLM + ML):', lastError?.message || lastError, mlErr?.message || mlErr);
      return res.status(502).json({
        success: false,
        message: `${msg} Groq/ML fallback also failed — set GROQ_API_KEY or start ml-api at ${ML_SERVICE_URL}.`,
      });
    }
  } catch (err) {
    console.error(err);
    return res.status(500).json({ success: false, message: 'Server error.' });
  }
});

// POST /api/scan/sms
router.post('/sms', async (req, res) => {
  try {
    const text = (req.body?.text || '').trim();
    if (!text || text.length < 2) {
      return res.status(400).json({ success: false, message: 'text is required.' });
    }
    const content = text.slice(0, 2000);
    const prompt = `You are an SMS scam detector. Your verdict and explanation MUST be consistent.

RULES:
- If the SMS has red flags (prize/winner, OTP pressure, bank/account suspension, click links, urgent action, toll numbers, lottery, "reply to win"), set verdict to "Scam" and score 60-100. Your explanation must describe WHY it is a scam.
- Only set verdict to "Legitimate" when there are no such red flags; then explain why it looks safe. Do NOT describe scam indicators in the explanation and then set "Legitimate"—if you found risks, set "Scam".

Respond with ONLY a valid JSON object (no markdown, no code block):
{"verdict": "Scam" or "Legitimate", "score": number 0-100 (100 = most likely scam), "reasons": ["reason1", "reason2"], "explanation": "2-4 sentences that match the verdict: either why it is a scam OR why it is legitimate."}

SMS content:
---
${content}
---`;
    const apiKeys = getApiKeys();
    let lastError = null;
    for (const key of apiKeys) {
      if (!key) continue;
      try {
        const raw = await callGemini(key, prompt);
        const parsed = parseJsonFromResponse(raw);
        const verdict = parsed && parsed.verdict ? String(parsed.verdict).trim() : '';
        if (parsed && (verdict === 'Scam' || verdict === 'Legitimate')) {
          return res.json({
            success: true,
            verdict,
            score: Math.min(100, Math.max(0, Number(parsed.score) || 50)),
            reasons: Array.isArray(parsed.reasons) ? parsed.reasons : [],
            explanation: parsed.explanation || null,
            extracted_text: text,
            source: 'gemini',
          });
        }
        if (raw && !parsed) {
          console.warn('Scan sms: Gemini response was not valid JSON. First 300 chars:', raw.slice(0, 300));
        }
      } catch (e) {
        lastError = e;
      }
    }

    const groqRaw = await tryGroqChatWithKeys(prompt, { maxTokens: 1024, temperature: 0.15 });
    if (groqRaw) {
      const parsed = parseJsonFromResponse(groqRaw);
      const verdict = parsed && parsed.verdict ? String(parsed.verdict).trim() : '';
      if (parsed && (verdict === 'Scam' || verdict === 'Legitimate')) {
        return res.json({
          success: true,
          verdict,
          score: Math.min(100, Math.max(0, Number(parsed.score) || 50)),
          reasons: Array.isArray(parsed.reasons) ? parsed.reasons : [],
          explanation: parsed.explanation || null,
          extracted_text: text,
          source: 'groq',
        });
      }
      if (!parsed) {
        console.warn('Scan sms: Groq response was not valid JSON. First 300 chars:', groqRaw.slice(0, 300));
      }
    }

    try {
      const out = await tryMlSms(text);
      return res.json(out);
    } catch (mlErr) {
      const msg = userFriendlyGeminiError(lastError);
      console.error('Scan sms failed (LLM + ML):', lastError?.message || lastError, mlErr?.message || mlErr);
      return res.status(502).json({
        success: false,
        message: `${msg} Groq/ML fallback also failed — set GROQ_API_KEY or start ml-api at ${ML_SERVICE_URL}.`,
      });
    }
  } catch (err) {
    console.error(err);
    return res.status(500).json({ success: false, message: 'Server error.' });
  }
});

// POST /api/scan/upi
router.post('/upi', async (req, res) => {
  try {
    const body = req.body || {};
    let content = (body.text || '').trim();
    if (!content) {
      const { amount, sender_upi, receiver_upi, time_of_day, day_of_week, transaction_type, is_new_recipient, device_changed } = body;
      content = `Amount: ${amount ?? 'N/A'}, Sender: ${sender_upi || 'N/A'}, Receiver: ${receiver_upi || 'N/A'}, Time: ${time_of_day ?? 'N/A'}, Day: ${day_of_week ?? 'N/A'}, Type: ${transaction_type || 'N/A'}, New recipient: ${is_new_recipient}, Device changed: ${device_changed}`;
    }
    if (!content || content.length < 2) {
      return res.status(400).json({ success: false, message: 'text or UPI fields required.' });
    }
    const textForResponse = content.slice(0, 2000);
    const now = new Date();
    const todayStr = now.toLocaleDateString('en-IN', { day: 'numeric', month: 'long', year: 'numeric' });
    const prompt = `You are a UPI payment fraud detector. Your verdict MUST match your explanation. If your explanation describes red flags, the verdict must NOT be "Legitimate".

IMPORTANT - Today's date is ${todayStr}. A transaction date is ONLY "in the future" if it is AFTER ${todayStr}. If the transaction date is before or on today, do NOT flag it as "future date". For example, 11 February 2026 is before ${todayStr}, so it is in the past—not a red flag.

UPI RED FLAGS (if ANY are present, use "Fraud" or "Suspicious" and high score 60-100):
- Transaction date is in the future (i.e. after ${todayStr}).
- UPI ID uses a non-standard or fake PSP handle: legitimate ones in India are @paytm, @okaxis, @ybl, @okicici, @axl, @ibl, @upi, @pnb, @sbi, @hdfc, @kotak, @phonepe, @googlepay, etc. Unknown handles like @slc, @xyz, @fake are NOT legitimate—treat as Fraud or Suspicious.
- Screenshot looks forged, edited, or like a fake receipt (e.g. mismatched formats, unrealistic amounts).
- Other signs of fake payment proof (e.g. to deceive someone).

RULES:
- If you find ANY red flag above (future date, non-standard/fake UPI handle, fake receipt), set verdict to "Fraud" or "Suspicious" and score 60-100. Your explanation must describe those red flags and say it is NOT genuine.
- Only set verdict to "Legitimate" when the transaction looks genuine: real bank/PSP handle, plausible date, no fake-receipt signs. Then explain why it looks safe. Never set "Legitimate" and then write an explanation that lists serious red flags like future date or fake UPI handle.

Respond with ONLY a valid JSON object (no markdown, no code block):
{"verdict": "Fraud" or "Suspicious" or "Legitimate", "score": number 0-100 (100 = highest fraud risk), "reasons": ["reason1", "reason2"], "explanation": "2-4 sentences that match the verdict: either list red flags and why it is fraud/suspicious, OR why it looks like a genuine transaction."}

Transaction/content:
---
${textForResponse}
---`;
    const apiKeys = getApiKeys();
    let lastError = null;
    for (const key of apiKeys) {
      if (!key) continue;
      try {
        const raw = await callGemini(key, prompt);
        const parsed = parseJsonFromResponse(raw);
        const verdict = parsed && parsed.verdict ? String(parsed.verdict).trim() : '';
        if (parsed && ['Fraud', 'Suspicious', 'Legitimate'].includes(verdict)) {
          const extracted_text = body.text || content;
          const parsed_fields = body.amount != null || body.receiver_upi ? {
            amount: body.amount,
            receiver_upi: body.receiver_upi,
            sender_upi: body.sender_upi,
            time: body.time_of_day != null ? `Hour: ${body.time_of_day}` : undefined,
            status: undefined,
          } : undefined;
          return res.json({
            success: true,
            verdict,
            score: Math.min(100, Math.max(0, Number(parsed.score) || 50)),
            reasons: Array.isArray(parsed.reasons) ? parsed.reasons : [],
            explanation: parsed.explanation || null,
            extracted_text: extracted_text || content,
            parsed_fields: parsed_fields || undefined,
            source: 'gemini',
          });
        }
        if (raw && !parsed) {
          console.warn('Scan upi: Gemini response was not valid JSON. First 300 chars:', raw.slice(0, 300));
        }
      } catch (e) {
        lastError = e;
      }
    }

    const groqRaw = await tryGroqChatWithKeys(prompt, { maxTokens: 1024, temperature: 0.15 });
    if (groqRaw) {
      const parsed = parseJsonFromResponse(groqRaw);
      const verdict = parsed && parsed.verdict ? String(parsed.verdict).trim() : '';
      if (parsed && ['Fraud', 'Suspicious', 'Legitimate'].includes(verdict)) {
        const extracted_text = body.text || content;
        const parsed_fields = body.amount != null || body.receiver_upi ? {
          amount: body.amount,
          receiver_upi: body.receiver_upi,
          sender_upi: body.sender_upi,
          time: body.time_of_day != null ? `Hour: ${body.time_of_day}` : undefined,
          status: undefined,
        } : undefined;
        return res.json({
          success: true,
          verdict,
          score: Math.min(100, Math.max(0, Number(parsed.score) || 50)),
          reasons: Array.isArray(parsed.reasons) ? parsed.reasons : [],
          explanation: parsed.explanation || null,
          extracted_text: extracted_text || content,
          parsed_fields: parsed_fields || undefined,
          source: 'groq',
        });
      }
      if (!parsed) {
        console.warn('Scan upi: Groq response was not valid JSON. First 300 chars:', groqRaw.slice(0, 300));
      }
    }

    try {
      const out = await tryMlUpi(body, content);
      return res.json(out);
    } catch (mlErr) {
      const msg = userFriendlyGeminiError(lastError);
      console.error('Scan upi failed (LLM + ML):', lastError?.message || lastError, mlErr?.message || mlErr);
      return res.status(502).json({
        success: false,
        message: `${msg} Groq/ML fallback also failed — set GROQ_API_KEY or start ml-api at ${ML_SERVICE_URL}.`,
      });
    }
  } catch (err) {
    console.error(err);
    return res.status(500).json({ success: false, message: 'Server error.' });
  }
});

module.exports = router;
