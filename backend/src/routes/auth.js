const express = require('express');
const { body, validationResult } = require('express-validator');
const jwt = require('jsonwebtoken');
const User = require('../models/User');
const { protect, JWT_SECRET } = require('../middleware/auth');

const router = express.Router();

const signToken = (id) => {
  return jwt.sign(
    { id },
    JWT_SECRET,
    { expiresIn: process.env.JWT_EXPIRES_IN || '7d' }
  );
};

// Validation rules
const registerRules = [
  body('fullName').trim().notEmpty().withMessage('Full name is required').isLength({ max: 100 }).withMessage('Name too long'),
  body('email').trim().isEmail().withMessage('Valid email is required').normalizeEmail(),
  body('phone').optional().trim(),
  body('password').isLength({ min: 6 }).withMessage('Password must be at least 6 characters'),
  body('confirmPassword').custom((value, { req }) => {
    if (value !== req.body.password) throw new Error('Passwords do not match');
    return true;
  }),
];

const loginRules = [
  body('email').trim().isEmail().withMessage('Valid email is required').normalizeEmail(),
  body('password').notEmpty().withMessage('Password is required'),
];

// POST /api/auth/register
router.post('/register', registerRules, async (req, res) => {
  try {
    const errors = validationResult(req);
    if (!errors.isEmpty()) {
      return res.status(400).json({ success: false, message: 'Validation failed', errors: errors.array() });
    }

    const { fullName, email, phone, password } = req.body;
    const existing = await User.findOne({ email });
    if (existing) {
      return res.status(400).json({ success: false, message: 'An account with this email already exists.' });
    }

    const user = await User.create({ fullName, email, phone: phone || '', password });
    const token = signToken(user._id);

    // Update last login for consistency
    await User.findByIdAndUpdate(user._id, { lastLoginAt: new Date() });

    res.status(201).json({
      success: true,
      message: 'Account created successfully.',
      data: {
        user: {
          id: user._id,
          fullName: user.fullName,
          email: user.email,
          phone: user.phone,
          role: user.role,
        },
        token,
        expiresIn: process.env.JWT_EXPIRES_IN || '7d',
      },
    });
  } catch (err) {
    console.error('Register error:', err);
    res.status(500).json({ success: false, message: 'Server error. Please try again.' });
  }
});

// POST /api/auth/login
router.post('/login', loginRules, async (req, res) => {
  try {
    const errors = validationResult(req);
    if (!errors.isEmpty()) {
      return res.status(400).json({ success: false, message: 'Validation failed', errors: errors.array() });
    }

    const { email, password } = req.body;
    const user = await User.findOne({ email }).select('+password');
    if (!user) {
      return res.status(401).json({ success: false, message: 'Invalid email or password.' });
    }
    if (!user.isActive) {
      return res.status(401).json({ success: false, message: 'Account is deactivated. Contact support.' });
    }

    const match = await user.comparePassword(password);
    if (!match) {
      return res.status(401).json({ success: false, message: 'Invalid email or password.' });
    }

    await User.findByIdAndUpdate(user._id, { lastLoginAt: new Date() });

    const token = signToken(user._id);

    res.json({
      success: true,
      message: 'Logged in successfully.',
      data: {
        user: {
          id: user._id,
          fullName: user.fullName,
          email: user.email,
          phone: user.phone,
          role: user.role,
        },
        token,
        expiresIn: process.env.JWT_EXPIRES_IN || '7d',
      },
    });
  } catch (err) {
    console.error('Login error:', err);
    res.status(500).json({ success: false, message: 'Server error. Please try again.' });
  }
});

// GET /api/auth/me - current user (protected)
router.get('/me', protect, (req, res) => {
  res.json({
    success: true,
    data: { user: req.user },
  });
});

// POST /api/auth/google - sign in / sign up with Google (body: { idToken } or { credential })
router.post('/google', async (req, res) => {
  try {
    const idToken = req.body?.idToken || req.body?.credential || '';
    if (!idToken) {
      return res.status(400).json({ success: false, message: 'Google idToken or credential is required.' });
    }

    const { OAuth2Client } = require('google-auth-library');
    const client = new OAuth2Client(process.env.GOOGLE_CLIENT_ID);
    const ticket = await client.verifyIdToken({
      idToken,
      audience: process.env.GOOGLE_CLIENT_ID,
    });
    const payload = ticket.getPayload();
    const googleId = payload.sub;
    const email = (payload.email || '').toLowerCase().trim();
    const fullName = payload.name || payload.email || 'User';

    if (!email) {
      return res.status(400).json({ success: false, message: 'Google account has no email. Use email/password sign up.' });
    }

    let user = await User.findOne({ $or: [{ googleId }, { email }] }).select('+password');
    if (user) {
      if (!user.googleId) {
        user.googleId = googleId;
        user.fullName = user.fullName || fullName;
        await user.save({ validateBeforeSave: false });
      }
      if (!user.isActive) {
        return res.status(401).json({ success: false, message: 'Account is deactivated. Contact support.' });
      }
    } else {
      user = await User.create({
        fullName,
        email,
        googleId,
      });
    }

    await User.findByIdAndUpdate(user._id, { lastLoginAt: new Date() });
    const token = signToken(user._id);
    const userObj = await User.findById(user._id).select('-password').lean();

    res.json({
      success: true,
      message: 'Signed in with Google.',
      data: {
        user: {
          id: userObj._id,
          fullName: userObj.fullName,
          email: userObj.email,
          phone: userObj.phone || '',
          role: userObj.role,
        },
        token,
        expiresIn: process.env.JWT_EXPIRES_IN || '7d',
      },
    });
  } catch (err) {
    console.error('Google auth error:', err);
    if (err.message && err.message.includes('Token used too late')) {
      return res.status(401).json({ success: false, message: 'Google sign-in expired. Try again.' });
    }
    res.status(401).json({ success: false, message: 'Google sign-in failed. Please try again.' });
  }
});

module.exports = router;
