const express = require('express');
const { body, param, validationResult } = require('express-validator');
const Plan = require('../models/Plan');
const { protect, requireAdmin } = require('../middleware/auth');

const router = express.Router();
router.use(protect);
router.use(requireAdmin);

// GET /api/admin/plans - list all plans
router.get('/', async (req, res) => {
  try {
    const plans = await Plan.find().sort({ sortOrder: 1, scansPerDay: 1 }).lean();
    res.json({ success: true, data: { plans } });
  } catch (err) {
    console.error('Admin plans list error:', err);
    res.status(500).json({ success: false, message: 'Server error.' });
  }
});

// POST /api/admin/plans - create plan
const createRules = [
  body('name').trim().notEmpty().withMessage('Name is required'),
  body('slug').trim().notEmpty().withMessage('Slug is required'),
  body('scansPerDay').isInt({ min: 0 }).withMessage('Scans per day must be a non-negative number'),
  body('price').optional().isFloat({ min: 0 }),
  body('interval').optional().isIn(['free', 'monthly', 'yearly']),
  body('isDefault').optional().isBoolean(),
  body('isActive').optional().isBoolean(),
  body('sortOrder').optional().isInt(),
];
router.post('/', createRules, async (req, res) => {
  try {
    const errors = validationResult(req);
    if (!errors.isEmpty()) {
      return res.status(400).json({ success: false, message: 'Validation failed', errors: errors.array() });
    }
    const { name, slug, scansPerDay, price, interval, isDefault, isActive, sortOrder } = req.body;
    if (isDefault) {
      await Plan.updateMany({}, { isDefault: false });
    }
    const plan = await Plan.create({
      name,
      slug: slug.toLowerCase().replace(/\s+/g, '-'),
      scansPerDay: parseInt(scansPerDay, 10),
      price: price != null ? parseFloat(price) : 0,
      interval: interval || 'free',
      isDefault: !!isDefault,
      isActive: isActive !== false,
      sortOrder: sortOrder != null ? parseInt(sortOrder, 10) : 0,
    });
    res.status(201).json({ success: true, message: 'Plan created.', data: { plan } });
  } catch (err) {
    if (err.code === 11000) {
      return res.status(400).json({ success: false, message: 'A plan with this slug already exists.' });
    }
    console.error('Admin create plan error:', err);
    res.status(500).json({ success: false, message: 'Server error.' });
  }
});

// PUT /api/admin/plans/:id
router.put('/:id', param('id').isMongoId(), body('name').optional().trim(), body('scansPerDay').optional().isInt({ min: 0 }), body('price').optional().isFloat({ min: 0 }), body('interval').optional().isIn(['free', 'monthly', 'yearly']), body('isDefault').optional().isBoolean(), body('isActive').optional().isBoolean(), body('sortOrder').optional().isInt(), async (req, res) => {
  try {
    const errors = validationResult(req);
    if (!errors.isEmpty()) {
      return res.status(400).json({ success: false, message: 'Validation failed', errors: errors.array() });
    }
    const { name, scansPerDay, price, interval, isDefault, isActive, sortOrder } = req.body;
    const update = {};
    if (name !== undefined) update.name = name;
    if (scansPerDay !== undefined) update.scansPerDay = parseInt(scansPerDay, 10);
    if (price !== undefined) update.price = parseFloat(price);
    if (interval !== undefined) update.interval = interval;
    if (isDefault !== undefined) {
      update.isDefault = isDefault;
      if (isDefault) await Plan.updateMany({ _id: { $ne: req.params.id } }, { isDefault: false });
    }
    if (isActive !== undefined) update.isActive = isActive;
    if (sortOrder !== undefined) update.sortOrder = parseInt(sortOrder, 10);

    const plan = await Plan.findByIdAndUpdate(req.params.id, { $set: update }, { new: true, runValidators: true });
    if (!plan) return res.status(404).json({ success: false, message: 'Plan not found.' });
    res.json({ success: true, message: 'Plan updated.', data: { plan } });
  } catch (err) {
    console.error('Admin update plan error:', err);
    res.status(500).json({ success: false, message: 'Server error.' });
  }
});

// DELETE /api/admin/plans/:id - deactivate (soft)
router.delete('/:id', param('id').isMongoId(), async (req, res) => {
  try {
    const plan = await Plan.findByIdAndUpdate(req.params.id, { isActive: false }, { new: true });
    if (!plan) return res.status(404).json({ success: false, message: 'Plan not found.' });
    res.json({ success: true, message: 'Plan deactivated.', data: { plan } });
  } catch (err) {
    console.error('Admin delete plan error:', err);
    res.status(500).json({ success: false, message: 'Server error.' });
  }
});

module.exports = router;