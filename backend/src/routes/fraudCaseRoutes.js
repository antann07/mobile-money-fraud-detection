const express = require('express');
const router = express.Router();
const {
  getFraudCases,
  getFraudCaseById
} = require('../controllers/fraudCaseController');

router.get('/', getFraudCases);
router.get('/:id', getFraudCaseById);

module.exports = router;