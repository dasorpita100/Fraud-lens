/**
 * One-time script to create an admin user. Run: node scripts/seedAdmin.js
 * Set ADMIN_EMAIL and ADMIN_PASSWORD in .env or pass as env vars.
 */
require('dotenv').config();
const mongoose = require('mongoose');
const User = require('../src/models/User');

const email = process.env.ADMIN_EMAIL || 'admin@fraudlens.com';
const password = process.env.ADMIN_PASSWORD || 'Admin@123';
const fullName = process.env.ADMIN_NAME || 'FraudLens Admin';

async function seed() {
  try {
    await mongoose.connect(process.env.MONGODB_URI || 'mongodb://localhost:27017/fraudlens');
    const existing = await User.findOne({ email });
    if (existing) {
      await User.findByIdAndUpdate(existing._id, { role: 'admin', isActive: true });
      console.log('Existing user updated to admin:', email);
    } else {
      await User.create({ fullName, email, password, role: 'admin' });
      console.log('Admin user created:', email);
    }
  } catch (err) {
    console.error('Seed error:', err.message);
  } finally {
    await mongoose.disconnect();
  }
}

seed();
