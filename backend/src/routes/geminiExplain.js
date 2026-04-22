/**
 * Explanation route: Gemini → Groq → Hugging Face → deterministic (ML-aligned) + URLhaus.
 * POST /api/gemini/explain - body: { scanType, contentPreview, verdict, score, reasons }
 */

const express = require('express');
const { tryGroqChatWithKeys } = require('../utils/groqClient');
const {
  buildDeterministicExplanationAsync,
  tryHuggingFaceExplanation,
} = require('../utils/explanationFallbacks');

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

function buildPrompt(scanType, contentPreview, verdict, score, reasons) {
  const content = (contentPreview || '').slice(0, 800);
  const reasonsText = Array.isArray(reasons) && reasons.length ? reasons.join(', ') : 'None listed';
  const isRisky = ['Phishing', 'Scam', 'Fraud', 'Suspicious'].includes(verdict);
  const st = (scanType || '').toLowerCase();

  if (st === 'email') {
    if (isRisky) {
      return `You are an email security expert. A user ran a phishing check on an email. Our AI classified it as **${verdict}** (risk score: ${score}/100). Technical signals: ${reasonsText}.

Email content (excerpt):
---
${content}
---

Give a clear, detailed explanation in 3–4 sentences:
1) WHY this was marked as suspicious/phishing (e.g. urgent language, suspicious links, sender mismatch, fake branding).
2) What specific red flags in the content support that.
3) What the user should do (e.g. do not click links, verify sender, contact the company directly).

Write in plain language. No bullet points in the final answer—use a short paragraph.`;
    }
    return `You are an email security expert. A user ran a phishing check on an email. Our AI classified it as **${verdict}** (risk score: ${score}/100). Technical signals: ${reasonsText}.

Email content (excerpt):
---
${content}
---

Give a clear, detailed explanation in 2–3 sentences:
1) WHY this was marked as legitimate/safe (e.g. normal tone, no urgent demands, no suspicious links, or expected sender).
2) What in the content suggests it is not a phishing attempt.

Write in plain language. No bullet points—use a short paragraph.`;
  }

  if (st === 'sms') {
    if (isRisky) {
      return `You are an SMS/scam prevention expert. A user ran a scam check on an SMS. Our AI classified it as **${verdict}** (risk score: ${score}/100). Technical signals: ${reasonsText}.

SMS content:
---
${content}
---

Give a clear, detailed explanation in 3–4 sentences:
1) WHY this was marked as scam/fraudulent (e.g. fake OTP, prize/lottery, urgent action, payment links, impersonation).
2) What specific phrases or patterns in the message are typical of SMS scams.
3) What the user should do (e.g. do not reply, do not share OTP, block the number, report).

Write in plain language. No bullet points—use a short paragraph.`;
    }
    return `You are an SMS/scam prevention expert. A user ran a scam check on an SMS. Our AI classified it as **${verdict}** (risk score: ${score}/100). Technical signals: ${reasonsText}.

SMS content:
---
${content}
---

Give a clear, detailed explanation in 2–3 sentences:
1) WHY this was marked as legitimate/safe (e.g. normal transactional message, known sender, no prize/OTP pressure).
2) What in the message suggests it is not a scam.

Write in plain language. No bullet points—use a short paragraph.`;
  }

  if (isRisky) {
    return `You are a UPI/digital payment fraud expert. A user ran a fraud check on a UPI payment or screenshot. Our AI classified it as **${verdict}** (risk score: ${score}/100). Technical signals: ${reasonsText}.

Transaction/content (excerpt):
---
${content}
---

Give a clear, detailed explanation in 3–4 sentences:
1) WHY this was marked as fraud/suspicious (e.g. odd time, large amount, new recipient, unknown UPI ID, device change).
2) What specific risk factors support that.
3) What the user should do (e.g. verify recipient, avoid paying until confirmed, contact bank if already paid).

Write in plain language. No bullet points—use a short paragraph.`;
  }
  return `You are a UPI/digital payment fraud expert. A user ran a fraud check on a UPI payment or screenshot. Our AI classified it as **${verdict}** (risk score: ${score}/100). Technical signals: ${reasonsText}.

Transaction/content (excerpt):
---
${content}
---

Give a clear, detailed explanation in 2–3 sentences:
1) WHY this was marked as legitimate/safe (e.g. normal amount, known recipient, typical timing, trusted UPI handle).
2) What in the transaction suggests lower fraud risk.

Write in plain language. No bullet points—use a short paragraph.`;
}

async function getExplanationFromGemini(apiKey, prompt) {
  const { GoogleGenerativeAI } = require('@google/generative-ai');
  const genAI = new GoogleGenerativeAI(apiKey);
  const model = genAI.getGenerativeModel({ model: 'gemini-2.5-flash' });
  const result = await model.generateContent(prompt);
  const response = result.response;
  if (response && response.text) {
    return response.text().trim();
  }
  return null;
}

// POST /api/gemini/explain
router.post('/explain', async (req, res) => {
  try {
    const { scanType, contentPreview, verdict, score, reasons } = req.body || {};
    if (!contentPreview || (typeof contentPreview === 'string' && contentPreview.trim().length < 5)) {
      return res.status(400).json({
        success: false,
        message: 'contentPreview is required and must have at least 5 characters.',
      });
    }

    const prompt = buildPrompt(
      scanType || 'email',
      contentPreview,
      verdict || 'Legitimate',
      score ?? 50,
      reasons || [],
    );

    const apiKeys = getApiKeys();

    for (const key of apiKeys) {
      if (!key) continue;
      try {
        const explanation = await getExplanationFromGemini(key, prompt);
        if (explanation) {
          return res.json({
            success: true,
            explanation,
            source: 'gemini',
          });
        }
      } catch (e) {
        console.warn('Gemini explain attempt failed:', e?.message || e);
      }
    }

    const groqText = await tryGroqChatWithKeys(prompt, { maxTokens: 512, temperature: 0.35 });
    if (groqText) {
      return res.json({
        success: true,
        explanation: groqText,
        source: 'groq',
      });
    }

    const hfText = await tryHuggingFaceExplanation(prompt);
    if (hfText) {
      return res.json({
        success: true,
        explanation: hfText,
        source: 'huggingface',
      });
    }

    const fallback = await buildDeterministicExplanationAsync(
      scanType || 'email',
      verdict || 'Legitimate',
      score ?? 50,
      reasons || [],
      contentPreview,
    );

    return res.json({
      success: true,
      explanation: fallback,
      source: 'deterministic',
      note: apiKeys.length
        ? 'LLM providers unavailable; used ML-aligned explanation (and optional link check).'
        : 'No Gemini/Groq keys or all failed; used ML-aligned explanation (and optional link check).',
    });
  } catch (err) {
    console.error(err);
    return res.status(500).json({ success: false, message: 'Server error.' });
  }
});

module.exports = router;
