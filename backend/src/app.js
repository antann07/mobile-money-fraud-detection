const express = require('express');
const cors = require('cors');
const morgan = require('morgan');

require('dotenv').config();

const authRoutes = require('./routes/authRoutes');
const transactionRoutes = require('./routes/transactionRoutes');
const fraudAlertRoutes = require('./routes/fraudAlertRoutes');
const fraudCaseRoutes = require('./routes/fraudCaseRoutes');
const dashboardRoutes = require('./routes/dashboardRoutes');

const app = express();

// Middleware setup
app.use(express.json()); // Parse incoming JSON requests
app.use(cors()); // Enable Cross-Origin Resource Sharing
app.use(morgan('dev')); // Log HTTP requests in development mode

// Basic routes
app.get('/', (req, res) => {
  res.send('Welcome to Unauthorized Mobile Money Withdrawal Detection System API');
});

app.get('/api/health', (req, res) => {
  res.status(200).json({ status: 'OK', message: 'Server is running' });
});

// Route registration
app.use('/api/auth', authRoutes);
app.use('/api/transactions', transactionRoutes);
app.use('/api/fraud-alerts', fraudAlertRoutes);
app.use('/api/fraud-cases', fraudCaseRoutes);
app.use('/api/dashboard', dashboardRoutes);

// Export the app for use in server.js
module.exports = app;