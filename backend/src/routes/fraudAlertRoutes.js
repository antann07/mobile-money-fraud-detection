const express = require('express');
const router = express.Router();
const {
  createFraudAlert,
  getFraudAlerts,
  getFraudAlertById,
  getAlertsByUserId,
  updateAlertStatus
} = require('../controllers/fraudAlertController');

router.post('/', createFraudAlert);
router.get('/', getFraudAlerts);
router.get('/user/:userId', getAlertsByUserId);
router.get('/:id', getFraudAlertById);
router.put('/:id/status', updateAlertStatus);

module.exports = router;
