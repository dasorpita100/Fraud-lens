const express = require('express');
const User = require('../models/User');
const Plan = require('../models/Plan');
const ScanHistory = require('../models/ScanHistory');
const { protect, requireAdmin } = require('../middleware/auth');

const router = express.Router();

function shouldResetDaily(user) {
  if (!user.scanCountResetAt) return true;
  const now = new Date();
  const reset = new Date(user.scanCountResetAt);
  return (
    now.getFullYear() !== reset.getFullYear() ||
    now.getMonth() !== reset.getMonth() ||
    now.getDate() !== reset.getDate()
  );
}

async function getEffectiveScanLimit(user) {
  if (user.dailyScanLimit != null) return user.dailyScanLimit;
  if (user.planId) {
    const plan = await Plan.findById(user.planId).lean();
    if (plan && plan.isActive) return plan.scansPerDay;
  }
  const defaultPlan = await Plan.findOne({ isDefault: true, isActive: true }).lean();
  return defaultPlan ? defaultPlan.scansPerDay : 5;
}

// User dashboard: own profile, stats, usage (protected)
router.get('/user', protect, async (req, res) => {
  try {
    const user = await User.findById(req.user.id).populate('planId', 'name slug scansPerDay price interval').lean();
    if (!user) {
      return res.status(404).json({ success: false, message: 'User not found.' });
    }
    let scanCount = user.scanCount || 0;
    if (shouldResetDaily(user)) scanCount = 0;
    const scanLimit = await getEffectiveScanLimit(user);

    const stats = {
      accountCreated: user.createdAt,
      lastLogin: user.lastLoginAt,
      scanCount,
      scanLimit,
      canScan: scanCount < scanLimit,
    };

    const recentScans = await ScanHistory.find({ user: req.user.id })
      .sort({ createdAt: -1 })
      .limit(40)
      .lean();

    res.json({
      success: true,
      data: {
        user: {
          id: user._id,
          fullName: user.fullName,
          email: user.email,
          phone: user.phone || '',
          role: user.role,
          isActive: user.isActive,
          createdAt: user.createdAt,
          planId: user.planId,
          credits: user.credits || 0,
        },
        stats,
        recentScans,
      },
    });
  } catch (err) {
    console.error('Dashboard user error:', err);
    res.status(500).json({ success: false, message: 'Server error.' });
  }
});

// Admin dashboard: overview stats (protected, admin only)
router.get('/admin', protect, requireAdmin, async (req, res) => {
  try {
    const [totalUsers, totalAdmins, activeUsers, totalScans] = await Promise.all([
      User.countDocuments(),
      User.countDocuments({ role: 'admin' }),
      User.countDocuments({ isActive: true }),
      ScanHistory.countDocuments(),
    ]);

    const recentUsers = await User.find()
      .select('fullName email role isActive createdAt lastLoginAt planId')
      .sort({ createdAt: -1 })
      .limit(10)
      .lean();

    const Payment = require('../models/Payment');
    const totalRevenue = await Payment.aggregate([
      { $match: { status: 'completed' } },
      { $group: { _id: null, total: { $sum: '$amount' } } },
    ]);

    res.json({
      success: true,
      data: {
        stats: {
          totalUsers,
          totalAdmins,
          activeUsers,
          totalScans,
          totalRevenue: totalRevenue[0]?.total || 0,
        },
        recentUsers,
      },
    });
  } catch (err) {
    console.error('Dashboard admin error:', err);
    res.status(500).json({ success: false, message: 'Server error.' });
  }
});

module.exports = router;