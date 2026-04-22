const mongoose = require('mongoose');

const connectDB = async () => {
  try {
    const conn = await mongoose.connect(process.env.MONGODB_URI || 'mongodb://localhost:27017/fraudlens', {
      // Avoid deprecation warnings
    });
    console.log(`MongoDB connected: ${conn.connection.host}`);

    // One-time fix: email/password users had googleId: null; sparse unique index only allows one null.
    const users = conn.connection.collection('users');
    const cleared = await users.updateMany(
      { $and: [{ googleId: { $exists: true } }, { googleId: null }] },
      { $unset: { googleId: '' } }
    );
    if (cleared.modifiedCount > 0) {
      console.log(`Cleared stale googleId:null on ${cleared.modifiedCount} user(s) for unique index compatibility.`);
    }
  } catch (err) {
    console.error('MongoDB connection error:', err.message);
    process.exit(1);
  }
};

module.exports = connectDB;
