const mongoose = require('mongoose');

const scanHistorySchema = new mongoose.Schema(
  {
    user: {
      type: mongoose.Schema.Types.ObjectId,
      ref: 'User',
      required: true,
      index: true,
    },
    scanType: {
      type: String,
      enum: ['email', 'sms', 'upi'],
      required: true,
    },
    verdict: {
      type: String,
      default: '',
      maxlength: 120,
    },
    score: {
      type: Number,
      default: 0,
      min: 0,
      max: 100,
    },
    preview: {
      type: String,
      default: '',
      maxlength: 500,
    },
    // Full content/text submitted by user
    content: {
      type: String,
      default: '',
    },
    // Image data stored as base64 (for UPI screenshots)
    imageData: {
      type: String,
      default: '',
    },
    // Full extracted text from OCR
    extractedText: {
      type: String,
      default: '',
    },
    // Parsed transaction fields (UPI)
    parsedFields: {
      type: mongoose.Schema.Types.Mixed,
      default: {},
    },
    // Full AI explanation
    explanation: {
      type: String,
      default: '',
    },
    // Reasons/findings array
    reasons: [{
      type: String,
    }],
  },
  { timestamps: true }
);

scanHistorySchema.index({ user: 1, createdAt: -1 });

const ScanHistory = mongoose.model('ScanHistory', scanHistorySchema);
module.exports = ScanHistory;