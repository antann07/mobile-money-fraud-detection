import axios from 'axios';

const api = axios.create({
  baseURL: 'http://localhost:5000/api',
  headers: {
    'Content-Type': 'application/json'
  }
});

export default api;

// other API helper functions can be added here using `api` (e.g., api.get('/auth/...'))
