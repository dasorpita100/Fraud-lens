const express = require('express');
const ContactSubmission = require('../models/ContactSubmission');
const { body, validationResult } = require('express-validator');

const router = express.Router();

const contactRules = [
  body('name').trim().notEmpty().withMessage('Name is required'),
  body('email').trim().isEmail().withMessage('Valid email is required'),
  body('subject').trim().notEmpty().withMessage('Subject is required'),
  body('message').trim().notEmpty().withMessage('Message is required'),
];

// POST /api/contact - public contact form submission
router.post('/', contactRules, async (req, res) => {
  try {
    const errors = validationResult(req);
    if (!errors.isEmpty()) {
      return res.status(400).json({
        success: false,
        message: 'Validation failed',
        errors: errors.array(),
      });
    }

    const { name, email, phone, subject, message } = req.body;
    const submission = await ContactSubmission.create({
      name,
      email,
      phone: phone || '',
      subject,
      message,
      status: 'new',
    });

    res.status(201).json({
      success: true,
      message: 'Thank you for contacting us! We will get back to you soon.',
      data: { id: submission._id },
    });
  } catch (err) {
    console.error('Contact submission error:', err);
    res.status(500).json({ success: false, message: 'Server error.' });
  }
});

module.exports = router;