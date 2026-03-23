const express = require('express');
const router = express.Router();
const {
  getDashboardSummary,
  getRecentTransactions,
  getRecentAlerts
} = require('../controllers/dashboardController');

router.get('/summary', getDashboardSummary);
router.get('/recent-transactions', getRecentTransactions);
router.get('/recent-alerts', getRecentAlerts);

module.exports = router;
