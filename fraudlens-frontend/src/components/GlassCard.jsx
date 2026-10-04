import React from 'react';
import './GlassCard.css';

export default function GlassCard({ title, description, icon, delay = 0 }) {
  return (
    <div 
      className="glass-card glass-panel"
      style={{ animationDelay: `${delay}s` }}
    >
      <div className="card-icon">{icon}</div>
      <h3 className="card-title">{title}</h3>
      <p className="card-description">{description}</p>
      
      <button className="card-btn">
        <span>Analyze Now</span>
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
      </button>
    </div>
  );
}
