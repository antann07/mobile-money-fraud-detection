import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../services/api';

const initialForm = {
  fullName: '',
  phoneNumber: '',
  transactionType: '',
  amount: '',
  location: '',
  status: '',
};

function CreateTransaction() {
  const navigate = useNavigate();
  const [form, setForm] = useState(initialForm);
  const [successMessage, setSuccessMessage] = useState('');
  const [errorMessage, setErrorMessage] = useState('');
  const [loading, setLoading] = useState(false);

  const handleChange = (e) => {
    setForm({ ...form, [e.target.name]: e.target.value });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSuccessMessage('');
    setErrorMessage('');
    setLoading(true);

    try {
      const savedUser = JSON.parse(localStorage.getItem('user') || '{}');
      const userId =
        savedUser.id ||
        savedUser._id ||
        '000000000000000000000001';

      const payload = {
        ...form,
        userId,
        timestamp: new Date().toISOString(),
        deviceId: navigator.userAgent || 'unknown-device',
      };

      await api.post('/transactions', payload);
      setSuccessMessage('Transaction created successfully!');
      setForm(initialForm);
      await new Promise((resolve) => setTimeout(resolve, 1000));
      navigate('/transactions');
    } catch (err) {
      setErrorMessage(
        err.response?.data?.message || 'Failed to create transaction. Please try again.'
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <div className="page-header">
        <h1>New Transaction</h1>
        <p>Submit a mobile money transaction for AI fraud analysis</p>
      </div>

      <div className="form-container">
        {successMessage && (
          <div className="message-box success">
            <span className="message-icon">✅</span>
            {successMessage}
          </div>
        )}
        {errorMessage && (
          <div className="message-box error">
            <span className="message-icon">❌</span>
            {errorMessage}
          </div>
        )}

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label htmlFor="fullName">Full Name</label>
            <input
              id="fullName"
              name="fullName"
              type="text"
              className="form-control"
              value={form.fullName}
              onChange={handleChange}
              required
              placeholder="e.g. John Doe"
            />
          </div>

          <div className="form-group">
            <label htmlFor="phoneNumber">Phone Number</label>
            <input
              id="phoneNumber"
              name="phoneNumber"
              type="tel"
              className="form-control"
              value={form.phoneNumber}
              onChange={handleChange}
              required
              placeholder="e.g. +233200000000"
            />
          </div>

          <div className="form-group">
            <label htmlFor="transactionType">Transaction Type</label>
            <select
              id="transactionType"
              name="transactionType"
              className="form-control"
              value={form.transactionType}
              onChange={handleChange}
              required
            >
              <option value="">-- Select Type --</option>
              <option value="withdrawal">Withdrawal</option>
              <option value="deposit">Deposit</option>
              <option value="transfer">Transfer</option>
            </select>
          </div>

          <div className="form-group">
            <label htmlFor="amount">Amount (GHS)</label>
            <input
              id="amount"
              name="amount"
              type="number"
              className="form-control"
              value={form.amount}
              onChange={handleChange}
              required
              min="0"
              placeholder="e.g. 500"
            />
          </div>

          <div className="form-group">
            <label htmlFor="location">Location</label>
            <input
              id="location"
              name="location"
              type="text"
              className="form-control"
              value={form.location}
              onChange={handleChange}
              required
              placeholder="e.g. Accra, Ghana"
            />
          </div>

          <div className="form-group">
            <label htmlFor="status">Status</label>
            <select
              id="status"
              name="status"
              className="form-control"
              value={form.status}
              onChange={handleChange}
              required
            >
              <option value="">-- Select Status --</option>
              <option value="pending">Pending</option>
              <option value="completed">Completed</option>
              <option value="failed">Failed</option>
            </select>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="btn btn-primary"
            style={{ width: '100%', padding: '0.7rem', marginTop: '0.5rem', fontSize: '0.9rem' }}
          >
            {loading ? 'Submitting...' : '➕ Submit Transaction'}
          </button>
        </form>
      </div>
    </div>
  );
}

export default CreateTransaction;
