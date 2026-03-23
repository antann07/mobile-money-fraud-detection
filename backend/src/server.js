require('dotenv').config();

const app = require('./app');
const connectDB = require('./config/db');

const PORT = process.env.PORT || 5000;

// Connect to the database before starting the server
connectDB();

// Start the Express server
app.listen(PORT, () => {
  console.log(`Server is running on port ${PORT}`);
});