const express = require('express');
const { body, param, validationResult } = require('express-validator');
const Payment = require('../models/Payment');
const User = require('../models/User');
const { protect, requireAdmin } = require('../middleware/auth');

const router = express.Router();
router.use(protect);
router.use(requireAdmin);

// GET /api/admin/payments - list all payments (paginated)
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
        { transactionId: new RegExp(search, 'i') },
        { description: new RegExp(search, 'i') },
      ];
    }

    const [payments, total] = await Promise.all([
      Payment.find(filter)
        .populate('user', 'fullName email')
        .populate('planId', 'name slug')
        .sort({ createdAt: -1 })
        .skip(skip)
        .limit(limit)
        .lean(),
      Payment.countDocuments(filter),
    ]);

    const revenue = await Payment.aggregate([
      { $match: { status: 'completed' } },
      { $group: { _id: null, total: { $sum: '$amount' }, count: { $sum: 1 } } },
    ]);

    res.json({
      success: true,
      data: {
        payments,
        pagination: { page, limit, total, totalPages: Math.ceil(total / limit) },
        revenue: { total: revenue[0]?.total || 0, count: revenue[0]?.count || 0 },
      },
    });
  } catch (err) {
    console.error('Admin payments list error:', err);
    res.status(500).json({ success: false, message: 'Server error.' });
  }
});

// GET /api/admin/payments/user/:userId - payments for specific user
router.get('/user/:userId', param('userId').isMongoId(), async (req, res) => {
  try {
    const errors = validationResult(req);
    if (!errors.isEmpty()) return res.status(400).json({ success: false, message: 'Invalid user ID.' });

    const payments = await Payment.find({ user: req.params.userId })
      .sort({ createdAt: -1 })
      .lean();

    res.json({ success: true, data: { payments } });
  } catch (err) {
    console.error('Admin user payments error:', err);
    res.status(500).json({ success: false, message: 'Server error.' });
  }
});

module.exports = router;