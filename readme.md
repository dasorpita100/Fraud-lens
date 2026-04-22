# FraudLens: AI-Powered Fraud Detection System

FraudLens is a comprehensive fraud detection platform that uses machine learning and generative AI to detect fraudulent activities across multiple channels:
- 🔐 **UPI Payment Screenshots** - Detects fake payment proofs
- 📧 **Phishing Emails** - Identifies malicious email attempts
- 📱 **Scam SMS & Messages** - Detects fraudulent text messages
- 🏦 **Forged Bank Statements** - Identifies fake financial documents

**Course Code:** CSE339: Capstone  
**Group Number:** CSERGC0392

---

## 🚀 Quick Start

---

## 📋 Table of Contents

- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
  - [Backend Setup](#backend-setup)
  - [Frontend Setup](#frontend-setup)
  - [ML API Setup](#ml-api-setup)
- [Configuration](#configuration)
- [Running the Project](#running-the-project)
- [Available Commands](#available-commands)
- [Troubleshooting](#troubleshooting)

---

## 📁 Project Structure

```
fraud-detection/
├── backend/                    # Node.js/Express backend (Port: 5000)
│   ├── src/
│   │   ├── server.js
│   │   ├── config/            # Database configuration
│   │   ├── middleware/        # Auth & custom middleware
│   │   ├── models/            # MongoDB schemas
│   │   ├── routes/            # API endpoints
│   │   ├── migrations/        # Database migrations
│   │   └── utils/             # Helper functions
│   ├── scripts/               # Utility scripts (seedAdmin.js)
│   └── package.json
│
├── fraudlens-frontend/        # React frontend (Port: 3000)
│   ├── public/
│   ├── src/
│   │   ├── components/        # React components
│   │   ├── pages/             # Page components
│   │   ├── api/               # API client
│   │   ├── utils/             # Utility functions
│   │   └── App.js
│   └── package.json
│
└── ml-api/                    # Python Flask ML API (Port: 8000)
    ├── app.py                 # Main Flask application
    ├── train/                 # Model training scripts
    ├── utils/                 # ML utility functions
    ├── models/                # Pre-trained models
    ├── requirements.txt       # Python dependencies
    └── .env                   # Environment variables
```

---

## 🔧 Prerequisites

### System Requirements

- **Windows/Mac/Linux** operating system
- **Git** (for cloning the repository)
- **Node.js** (v16 or higher) - [Download](https://nodejs.org/)
- **Python** (v3.8 or higher) - [Download](https://www.python.org/)
- **MongoDB** Atlas account (free tier available) - [Sign up](https://www.mongodb.com/cloud/atlas)
- **Google Cloud API Keys:**
  - Google Generative AI API key
  - Google OAuth 2.0 credentials (for authentication)

### Windows-Specific Requirements

**Tesseract OCR Installation** (required for image text extraction):

1. Download the installer: [Tesseract-OCR Installer](https://github.com/tesseract-ocr/tesseract/wiki/Downloads)
2. Run the installer (default path: `C:\Program Files\Tesseract-OCR`)
3. The application auto-detects the installation path on Windows

---

## 📦 Installation

### Backend Setup

1. **Navigate to the backend directory:**
   ```bash
   cd backend
   ```

2. **Install dependencies:**
   ```bash
   npm install
   ```

3. **Configure environment variables:**

   Create a `.env` file in the `backend/` directory with the following variables:

   ```env
   # Database Configuration
   MONGODB_URI=mongodb+srv://username:password@cluster.mongodb.net/fraudlens
   
   # Server Configuration
   PORT=5000
   NODE_ENV=development
   
   # JWT Secret for authentication
   JWT_SECRET=your_jwt_secret_key_min_32_characters_long
   
   # Google Generative AI
   GOOGLE_GENERATIVE_AI_API_KEY=your_google_generative_ai_key
   
   # Google OAuth (for login)
   GOOGLE_CLIENT_ID=your_google_client_id
   GOOGLE_CLIENT_SECRET=your_google_client_secret
   
   # Frontend URL
   REACT_APP_API_URL=http://localhost:5000
   ```

4. **Initialize the database (optional - for admin user setup):**
   ```bash
   node scripts/seedAdmin.js
   ```

---

### Frontend Setup

1. **Navigate to the frontend directory:**
   ```bash
   cd fraudlens-frontend
   ```

2. **Install dependencies:**
   ```bash
   npm install
   ```

3. **Configure environment variables:**

   Create a `.env` file in the `fraudlens-frontend/` directory:

   ```env
   # Backend API URL
   REACT_APP_API_URL=http://localhost:5000
   
   # ML API URL
   REACT_APP_ML_API_URL=http://localhost:8000
   
   # Google OAuth Client ID
   REACT_APP_GOOGLE_CLIENT_ID=your_google_client_id
   ```

---

### ML API Setup

1. **Navigate to the ML API directory:**
   ```bash
   cd ml-api
   ```

2. **Create a Python virtual environment:**

   ```bash
   # Windows
   python -m venv venv
   venv\Scripts\activate
   
   # Mac/Linux
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables:**

   Create a `.env` file in the `ml-api/` directory:

   ```env
   # Gemini API Key for fraud explanations
   GEMINI_API_KEY=your_google_generative_ai_key
   
   # Flask Configuration
   FLASK_ENV=development
   
   # Tesseract OCR Path (Windows only, auto-detected if installed)
   TESSERACT_PATH=C:\Program Files\Tesseract-OCR\tesseract.exe
   ```

5. **Verify Tesseract Installation (Windows):**
   ```bash
   python -c "import pytesseract; pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'; pytesseract.get_languages()"
   ```

---

## ⚙️ Configuration

### MongoDB Setup

1. **Create a MongoDB Atlas Cluster:**
   - Visit [MongoDB Atlas](https://www.mongodb.com/cloud/atlas)
   - Create a free account
   - Build a cluster
   - Create a database user with username and password
   - Get your connection string

2. **Add Connection String to Backend `.env`:**
   ```env
   MONGODB_URI=mongodb+srv://username:password@cluster0.xxxxx.mongodb.net/fraudlens
   ```

### Google API Keys

1. **Get Generative AI API Key:**
   - Go to [Google AI Studio](https://makersuite.google.com/app/apikey)
   - Create a new API key
   - Add to both `.env` files (backend and ml-api)

2. **Setup Google OAuth for Login:**
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project
   - Enable Google+ API
   - Create OAuth 2.0 credentials (Web application)
   - Add authorized redirect URIs:
     - `http://localhost:3000`
     - `http://localhost:3000/login`
   - Copy Client ID and Secret to backend `.env`

---

## 🚀 Running the Project

### Option 1: Run All Services Individually (Recommended for Development)

**Terminal 1 - Backend:**
```bash
cd backend
npm run dev
# Server runs on http://localhost:5000
```

**Terminal 2 - ML API:**
```bash
cd ml-api
# Activate virtual environment (if not already)
# Windows: venv\Scripts\activate
# Mac/Linux: source venv/bin/activate
python app.py
# Server runs on http://localhost:8000
```

**Terminal 3 - Frontend:**
```bash
cd fraudlens-frontend
npm start
# Application opens on http://localhost:3000
```

### Option 2: Run Services in Parallel (PowerShell)

Create a file `start-all.ps1`:

```powershell
# Start Backend
Start-Process powershell -ArgumentList "cd backend; npm run dev"

# Start ML API
Start-Process powershell -ArgumentList "cd ml-api; venv\Scripts\activate; python app.py"

# Start Frontend
Start-Process powershell -ArgumentList "cd fraudlens-frontend; npm start"

Write-Host "All services started!"
Write-Host "Frontend: http://localhost:3000"
Write-Host "Backend: http://localhost:5000"
Write-Host "ML API: http://localhost:8000"
```

Run with:
```bash
.\start-all.ps1
```

---

## 📚 Available Commands

### Backend

```bash
cd backend

# Development mode (auto-reload on file changes)
npm run dev

# Production mode
npm start
```

### Frontend

```bash
cd fraudlens-frontend

# Start development server with hot reload
npm start

# Build for production
npm run build

# Run tests
npm test

# Eject configuration (one-way operation)
npm run eject
```

### ML API

```bash
cd ml-api

# Activate virtual environment
# Windows: venv\Scripts\activate
# Mac/Linux: source venv/bin/activate

# Run development server
python app.py

# Train models (if needed)
python train/train_email.py
python train/train_sms.py
python train/train_upi.py
```

---

## 🔌 API Endpoints

### Backend (Port 5000)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/auth/register` | User registration |
| POST | `/api/auth/login` | User login |
| POST | `/api/auth/logout` | User logout |
| GET | `/api/dashboard` | User dashboard data |
| POST | `/api/scan` | Submit scan request |
| GET | `/api/usage` | Get scan usage |
| GET | `/api/plans` | Get pricing plans |
| POST | `/api/contact` | Submit contact form |

### ML API (Port 8000)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/scan/upi` | Analyze UPI screenshot |
| POST | `/scan/email` | Scan email for phishing |
| POST | `/scan/sms` | Scan SMS for fraud |
| POST | `/scan/bank-statement` | Analyze bank statement |

---

## 🔒 Security Considerations

1. **Never commit `.env` files** - Add to `.gitignore`
2. **Use strong JWT secrets** - Minimum 32 characters
3. **Enable CORS properly** - Only allow frontend URLs in production
4. **Validate all inputs** - Backend uses `express-validator`
5. **Use HTTPS in production** - Never use HTTP for sensitive data
6. **Keep API keys secure** - Use environment variables only
7. **Set rate limits** - Backend implements `express-rate-limit`

---

## 🐛 Troubleshooting

### MongoDB Connection Error
```
Error: connect ECONNREFUSED
```
**Solution:**
- Check MongoDB URI in `.env`
- Ensure MongoDB is running
- Verify network access in MongoDB Atlas

### Port Already in Use
```
Error: listen EADDRINUSE: address already in use :::5000
```
**Solution:**
- Windows: `netstat -ano | findstr :5000` then `taskkill /PID <PID> /F`
- Mac/Linux: `lsof -ti:5000 | xargs kill -9`

### Tesseract Not Found (Windows)
```
Error: TesseractNotFoundError
```
**Solution:**
1. Install Tesseract from: https://github.com/tesseract-ocr/tesseract/wiki/Downloads
2. Verify path: `C:\Program Files\Tesseract-OCR\tesseract.exe` exists
3. Restart the ML API service

### CORS Errors
```
Error: Access to XMLHttpRequest blocked by CORS policy
```
**Solution:**
- Check `.env` file for correct API URLs
- Ensure backend CORS allows frontend origin
- Restart services after changing URLs

### Google API Key Issues
```
Error: 403 Forbidden - API key not valid
```
**Solution:**
- Verify API key is active in Google Cloud Console
- Check billing is enabled
- Ensure correct key is in `.env`

### Virtual Environment Not Activated (Python)
```
ModuleNotFoundError: No module named 'flask'
```
**Solution:**
```bash
# Windows
cd ml-api
venv\Scripts\activate
pip install -r requirements.txt

# Mac/Linux
cd ml-api
source venv/bin/activate
pip install -r requirements.txt
```

### Node Modules Not Installed
```
Error: Cannot find module 'express'
```
**Solution:**
```bash
cd backend  # or fraudlens-frontend
npm install
```

---

## 📱 Usage Guide

1. **Register/Login** - Create account or login with Google OAuth
2. **Choose a Plan** - Select Free, Basic, or Pro plan
3. **Submit Content** - Upload screenshot, email, SMS, or bank statement
4. **View Results** - Get fraud probability and AI-powered explanation
5. **Check History** - View past scans in dashboard

---

## 📝 Tech Stack

- **Backend:** Node.js, Express, MongoDB, JWT, Google Generative AI
- **Frontend:** React, React Router, TailwindCSS, Tesseract.js
- **ML/AI:** Python, Flask, scikit-learn, XGBoost, Google Gemini API

---

## 👥 Project Team

### Developers & Roles

| Role | Members | Responsibilities |
|------|---------|-----------------|
| **Full Stack Development** | Aman Yadav, Saurabh Kumar Choubey, Alok Upadhayay | Frontend & Backend Implementation |
| **Cybersecurity** | Surya Prakash | Security, OWASP Compliance, Penetration Testing |
| **Software Testing** | Ritik Kumar, Aryan Aditya | QA, Functional Testing, AI Validation |

---

## 📄 License

MIT License - See LICENSE file for details

---

## 🤝 Support

For issues or questions:
1. Check the Troubleshooting section
2. Review project documentation
3. Check GitHub issues
4. Contact development team

---

## ✅ Getting Started Checklist

- [ ] Install Node.js and Python
- [ ] Install Tesseract OCR (Windows)
- [ ] Clone/download the project
- [ ] Set up MongoDB Atlas
- [ ] Get Google API keys
- [ ] Create `.env` files in backend, frontend, and ml-api
- [ ] Install backend dependencies: `npm install`
- [ ] Install frontend dependencies: `npm install`
- [ ] Install ML API dependencies: `pip install -r requirements.txt`
- [ ] Start all three services
- [ ] Visit http://localhost:3000

---

**Last Updated:** April 2026
**Version:** 1.0.0
 