import React, { useEffect, useState, useRef } from 'react';
import BlobBackground from './components/BlobBackground';
import GlassCard from './components/GlassCard';
import './App.css';

function App() {
  const [selectedScanner, setSelectedScanner] = useState(null);
  const [inputText, setInputText] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  
  const modalRef = useRef(null);

  // Interactive hover effect for cards
  useEffect(() => {
    const handleMouseMove = (e) => {
      for (const card of document.querySelectorAll('.glass-card')) {
        const rect = card.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        card.style.setProperty('--mouse-x', `${x}px`);
        card.style.setProperty('--mouse-y', `${y}px`);
      }
    };
    
    document.addEventListener('mousemove', handleMouseMove);
    return () => document.removeEventListener('mousemove', handleMouseMove);
  }, []);

  const handleCardClick = (type) => {
    setSelectedScanner(type);
    setInputText('');
    setResult(null);
    setError(null);
    setTimeout(() => {
      modalRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, 100);
  };

  const handleScan = async () => {
    if (!inputText.trim()) {
      setError('Please enter some text to analyze.');
      return;
    }
    
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const response = await fetch(`http://localhost:5002/api/scan/${selectedScanner}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ text: inputText }),
      });

      const data = await response.json();
      
      if (!response.ok || !data.success) {
        throw new Error(data.message || 'Analysis failed. Make sure backend/ML services are running.');
      }

      setResult(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const getScannerTitle = () => {
    if (selectedScanner === 'email') return 'Phishing Email Scanner';
    if (selectedScanner === 'sms') return 'Scam SMS Scanner';
    if (selectedScanner === 'upi') return 'UPI Fraud Scanner';
    return '';
  };

  return (
    <>
      <BlobBackground />
      
      <div className="app-container">
        <header className="header">
          <div className="logo">
            <span className="logo-icon">🛡️</span>
            <span className="logo-text">Fraud<span className="text-gradient">Lens</span></span>
          </div>
          <nav className="nav">
            <a href="#dashboard" className="nav-link active">Dashboard</a>
            <button className="auth-btn glass-panel" onClick={() => window.location.reload()}>Reset</button>
          </nav>
        </header>

        <main className="main-content">
          <div className="hero">
            <h1 className="hero-title">
              Detect Fraud with <br/>
              <span className="text-gradient">AI Precision</span>
            </h1>
            <p className="hero-subtitle">
              Select a category below and paste the suspicious content. Our multi-modal AI immediately identifies forgery, phishing attempts, and scams.
            </p>
          </div>

          <div className="scanners-grid">
            <div onClick={() => handleCardClick('upi')}>
              <GlassCard 
                title="UPI Payments" 
                description="Analyze UPI transaction details or receipt text to detect forged receipts and fake transactions instantly."
                icon="💸"
                delay={0.1}
              />
            </div>
            <div onClick={() => handleCardClick('email')}>
              <GlassCard 
                title="Phishing Emails" 
                description="Scan suspicious email content to identify malicious links, spoofed senders, and social engineering."
                icon="📧"
                delay={0.2}
              />
            </div>
            <div onClick={() => handleCardClick('sms')}>
              <GlassCard 
                title="Scam SMS" 
                description="Analyze text messages and WhatsApp chats for common fraud patterns and urgent requests."
                icon="💬"
                delay={0.3}
              />
            </div>
          </div>

          {selectedScanner && (
            <div className="analysis-section glass-panel" ref={modalRef}>
              <div className="analysis-header">
                <h2>{getScannerTitle()}</h2>
                <button className="close-btn" onClick={() => setSelectedScanner(null)}>✕</button>
              </div>
              
              <div className="input-group">
                <label>Paste the suspicious content here:</label>
                <textarea 
                  value={inputText}
                  onChange={(e) => setInputText(e.target.value)}
                  placeholder="e.g. Dear customer, your account will be suspended..."
                  rows={6}
                ></textarea>
              </div>
              
              {error && <div className="error-message">{error}</div>}
              
              <button 
                className={`scan-btn ${loading ? 'loading' : ''}`} 
                onClick={handleScan}
                disabled={loading}
              >
                {loading ? 'Analyzing with AI...' : 'Analyze Now'}
              </button>

              {result && (
                <div className="results-container">
                  <div className="result-header">
                    <div className={`verdict-badge ${result.verdict?.toLowerCase()}`}>
                      {result.verdict}
                    </div>
                    <div className="score-indicator">
                      Risk Score: <strong>{result.score}/100</strong>
                    </div>
                  </div>
                  
                  <div className="result-body">
                    <div className="explanation">
                      <h4>AI Explanation</h4>
                      <p>{result.explanation}</p>
                    </div>
                    
                    {result.reasons && result.reasons.length > 0 && (
                      <div className="reasons">
                        <h4>Key Indicators</h4>
                        <ul>
                          {result.reasons.map((r, i) => <li key={i}>{r}</li>)}
                        </ul>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}
        </main>
      </div>
    </>
  );
}

export default App;
