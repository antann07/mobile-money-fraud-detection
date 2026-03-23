import React from "react";
import { BrowserRouter as Router, Routes, Route, Navigate } from "react-router-dom";
import Navbar from "./components/Navbar";
import Sidebar from "./components/Sidebar";
import Dashboard from "./pages/Dashboard";
import Transactions from "./pages/Transactions";
import FraudAlerts from "./pages/FraudAlerts";
import FraudCases from "./pages/FraudCases";
import CreateTransaction from "./pages/CreateTransaction";
import "./App.css";

function App() {
  return (
    <Router>
      <div className="app-layout">
        <Navbar />
        <div className="main-content">
          <Sidebar />
          <div className="page-content">
            <Routes>
              <Route path="/" element={<Navigate to="/dashboard" replace />} />
              <Route path="/dashboard" element={<Dashboard />} />
              <Route path="/transactions" element={<Transactions />} />
              <Route path="/fraud-alerts" element={<FraudAlerts />} />
              <Route path="/fraud-cases" element={<FraudCases />} />
              <Route path="/create-transaction" element={<CreateTransaction />} />
            </Routes>
          </div>
        </div>
      </div>
    </Router>
  );
}

export default App;

