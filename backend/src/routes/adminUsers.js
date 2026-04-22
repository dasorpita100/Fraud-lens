const express = require('express');
const { body, param, validationResult } = require('express-validator');
const User = require('../models/User');
const { protect, requireAdmin } = require('../middleware/auth');

const router = express.Router();

// All routes require auth + admin
router.use(protect);
router.use(requireAdmin);

// GET /api/admin/users - list users (paginated)
router.get('/', async (req, res) => {
  try {
    const page = Math.max(1, parseInt(req.query.page, 10) || 1);
    const limit = Math.min(50, Math.max(1, parseInt(req.query.limit, 10) || 10));
    const skip = (page - 1) * limit;
    const search = (req.query.search || '').trim();
    const roleFilter = req.query.role; // 'user' | 'admin'
    const activeFilter = req.query.isActive; // 'true' | 'false'

    const filter = {};
    if (search) {
      filter.$or = [
        { fullName: new RegExp(search, 'i') },
        { email: new RegExp(search, 'i') },
      ];
    }
    if (roleFilter === 'user' || roleFilter === 'admin') filter.role = roleFilter;
    if (activeFilter === 'true') filter.isActive = true;
    if (activeFilter === 'false') filter.isActive = false;

    const [users, total] = await Promise.all([
      User.find(filter).select('-password').populate('planId', 'name slug scanLimit').sort({ createdAt: -1 }).skip(skip).limit(limit).lean(),
      User.countDocuments(filter),
    ]);

    res.json({
      success: true,
      data: {
        users,
        pagination: {
          page,
          limit,
          total,
          totalPages: Math.ceil(total / limit),
        },
      },
    });
  } catch (err) {
    console.error('Admin list users error:', err);
    res.status(500).json({ success: false, message: 'Server error.' });
  }
});

// GET /api/admin/users/:id - get one user
router.get('/:id', param('id').isMongoId(), async (req, res) => {
  try {
    const errors = validationResult(req);
    if (!errors.isEmpty()) {
      return res.status(400).json({ success: false, message: 'Invalid user ID.' });
    }

    const user = await User.findById(req.params.id).select('-password').lean();
    if (!user) {
      return res.status(404).json({ success: false, message: 'User not found.' });
    }

    res.json({ success: true, data: { user } });
  } catch (err) {
    console.error('Admin get user error:', err);
    res.status(500).json({ success: false, message: 'Server error.' });
  }
});

// PUT /api/admin/users/:id - update user (role, isActive, fullName, phone, planId; not password/email here)
const updateRules = [
  param('id').isMongoId(),
  body('fullName').optional().trim().isLength({ max: 100 }),
  body('phone').optional().trim(),
  body('role').optional().isIn(['user', 'admin']),
  body('isActive').optional().isBoolean(),
  body('planId').optional().isMongoId().withMessage('Invalid plan ID'),
  body('dailyScanLimit').optional().isInt({ min: 1 }).withMessage('Daily scan limit must be a positive number'),
];
router.put('/:id', updateRules, async (req, res) => {
  try {
    const errors = validationResult(req);
    if (!errors.isEmpty()) {
      return res.status(400).json({ success: false, message: 'Validation failed', errors: errors.array() });
    }

    const { fullName, phone, role, isActive, planId, dailyScanLimit, credits } = req.body;
    const update = {};
    if (fullName !== undefined) update.fullName = fullName;
    if (phone !== undefined) update.phone = phone;
    if (role !== undefined) update.role = role;
    if (isActive !== undefined) update.isActive = isActive;
    if (planId !== undefined) update.planId = planId || null;
    if (dailyScanLimit !== undefined) update.dailyScanLimit = dailyScanLimit;
    if (credits !== undefined) update.credits = Math.max(0, credits);

    const user = await User.findByIdAndUpdate(
      req.params.id,
      { $set: update },
      { new: true, runValidators: true }
    ).select('-password');

    if (!user) {
      return res.status(404).json({ success: false, message: 'User not found.' });
    }

    res.json({ success: true, message: 'User updated.', data: { user } });
  } catch (err) {
    console.error('Admin update user error:', err);
    res.status(500).json({ success: false, message: 'Server error.' });
  }
});

// DELETE /api/admin/users/:id - delete user (or deactivate; here we soft-delete by isActive)
router.delete('/:id', param('id').isMongoId(), async (req, res) => {
  try {
    const errors = validationResult(req);
    if (!errors.isEmpty()) {
      return res.status(400).json({ success: false, message: 'Invalid user ID.' });
    }

    const id = req.params.id;
    if (id === req.user.id) {
      return res.status(400).json({ success: false, message: 'You cannot delete your own account.' });
    }

    const user = await User.findByIdAndUpdate(id, { isActive: false }, { new: true }).select('-password');
    if (!user) {
      return res.status(404).json({ success: false, message: 'User not found.' });
    }

    res.json({ success: true, message: 'User deactivated.', data: { user } });
  } catch (err) {
    console.error('Admin delete user error:', err);
    res.status(500).json({ success: false, message: 'Server error.' });
  }
});

module.exports = router;
