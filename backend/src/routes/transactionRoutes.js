const express = require('express');
const router = express.Router();
const { createTransaction, getTransactions, getTransactionById } = require('../controllers/transactionController');

router.post('/', createTransaction);
router.get('/', getTransactions);
router.get('/:id', getTransactionById);

module.exports = router;