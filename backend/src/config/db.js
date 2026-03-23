const mongoose = require('mongoose');

// Function to connect to MongoDB Atlas using Mongoose
const connectDB = async () => {
  try {
    // Connect to MongoDB using the URI from environment variables
    await mongoose.connect(process.env.MONGO_URI);
    console.log('MongoDB connected successfully');
  } catch (error) {
    // Log the error and exit if connection fails
    console.error('MongoDB connection error:', error);
    process.exit(1);
  }
};

module.exports = connectDB;