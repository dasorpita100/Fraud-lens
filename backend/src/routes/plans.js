const express = require('express');
const mongoose = require('mongoose');
const Plan = require('../models/Plan');
const User = require('../models/User');
const { protect } = require('../middleware/auth');

const router = express.Router();

// GET /api/plans - list active plans (public, for pricing/upgrade)
router.get('/', async (req, res) => {
  try {
    const plans = await Plan.find({ isActive: true })
      .sort({ sortOrder: 1, scansPerDay: 1 })
      .lean();
    res.json({ success: true, data: { plans } });
  } catch (err) {
    console.error('Plans list error:', err);
    res.status(500).json({ success: false, message: 'Server error.' });
  }
});

/**
 * POST /api/plans/select — MVP mock enrollment (no payment). Assigns plan to the logged-in user.
 * Body: { planId?: string, planSlug?: string }
 */
router.post('/select', protect, async (req, res) => {
  try {
    const { planId, planSlug } = req.body || {};
    let plan = null;
    if (planId && mongoose.Types.ObjectId.isValid(planId)) {
      plan = await Plan.findOne({ _id: planId, isActive: true }).lean();
    }
    if (!plan && planSlug) {
      const slug = String(planSlug).toLowerCase().trim();
      plan = await Plan.findOne({ slug, isActive: true }).lean();
    }
    if (!plan) {
      return res.status(404).json({ success: false, message: 'Plan not found or inactive.' });
    }

    await User.findByIdAndUpdate(req.user.id, { planId: plan._id });
    const updated = await User.findById(req.user.id).populate('planId', 'name slug scanLimit price interval').lean();

    res.json({
      success: true,
      message: 'Plan updated (demo enrollment — no charge).',
      data: {
        plan: updated.planId,
        user: {
          id: updated._id,
          fullName: updated.fullName,
          email: updated.email,
          planId: updated.planId,
        },
      },
    });
  } catch (err) {
    console.error('Plan select error:', err);
    res.status(500).json({ success: false, message: 'Server error.' });
  }
});

module.exports = router;
