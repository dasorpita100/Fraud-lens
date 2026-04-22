const express = require('express');
const { body, param, validationResult } = require('express-validator');
const ContactSubmission = require('../models/ContactSubmission');
const { protect, requireAdmin } = require('../middleware/auth');

const router = express.Router();
router.use(protect);
router.use(requireAdmin);

// GET /api/admin/contacts - list contact submissions (paginated)
router.get('/', async (req, res) => {
  try {
    const page = Math.max(1, parseInt(req.query.page, 10) || 1);
    const limit = Math.min(50, Math.max(1, parseInt(req.query.limit, 10) || 10));
    const skip = (page - 1) * limit;
    const status = req.query.status;
    const search = (req.query.search || '').trim();

    const filter = {};
    if (status) filter.status = status;
    if (search) {
      filter.$or = [
        { name: new RegExp(search, 'i') },
        { email: new RegExp(search, 'i') },
        { subject: new RegExp(search, 'i') },
      ];
    }

    const [submissions, total] = await Promise.all([
      ContactSubmission.find(filter)
        .sort({ createdAt: -1 })
        .skip(skip)
        .limit(limit)
        .lean(),
      ContactSubmission.countDocuments(filter),
    ]);

    const newCount = await ContactSubmission.countDocuments({ status: 'new' });

    res.json({
      success: true,
      data: {
        submissions,
        pagination: { page, limit, total, totalPages: Math.ceil(total / limit) },
        newCount,
      },
    });
  } catch (err) {
    console.error('Admin contacts list error:', err);
    res.status(500).json({ success: false, message: 'Server error.' });
  }
});

// PUT /api/admin/contacts/:id - update status / reply
router.put('/:id', param('id').isMongoId(), async (req, res) => {
  try {
    const errors = validationResult(req);
    if (!errors.isEmpty()) return res.status(400).json({ success: false, message: 'Invalid ID.' });

    const { status, replyMessage } = req.body;
    const update = {};
    if (status) update.status = status;
    if (replyMessage !== undefined) {
      update.replyMessage = replyMessage;
      update.repliedAt = replyMessage ? new Date() : null;
    }

    const submission = await ContactSubmission.findByIdAndUpdate(
      req.params.id,
      { $set: update },
      { new: true }
    ).lean();

    if (!submission) return res.status(404).json({ success: false, message: 'Submission not found.' });
    res.json({ success: true, message: 'Updated.', data: { submission } });
  } catch (err) {
    console.error('Admin update contact error:', err);
    res.status(500).json({ success: false, message: 'Server error.' });
  }
});

module.exports = router;