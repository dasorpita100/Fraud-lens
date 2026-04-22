const mongoose = require('mongoose');

const planSchema = new mongoose.Schema(
  {
    name: {
      type: String,
      required: true,
      trim: true,
      maxlength: [80, 'Plan name too long'],
    },
    slug: {
      type: String,
      required: true,
      unique: true,
      trim: true,
      lowercase: true,
    },
    scansPerDay: {
      type: Number,
      required: true,
      min: 0,
    },
    price: {
      type: Number,
      default: 0,
      min: 0,
    },
    interval: {
      type: String,
      enum: ['free', 'monthly', 'yearly'],
      default: 'free',
    },
    isDefault: {
      type: Boolean,
      default: false,
    },
    isActive: {
      type: Boolean,
      default: true,
    },
    sortOrder: {
      type: Number,
      default: 0,
    },
  },
  { timestamps: true }
);

const Plan = mongoose.model('Plan', planSchema);
module.exports = Plan;