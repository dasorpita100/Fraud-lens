# FraudLens Backend

Backend for **FraudLens** (AI-powered fraud detection). Provides user authentication (login/sign up), user and admin dashboards, and admin user management. Database: **MongoDB**.

## Features

- **Auth**: Register, Login, Get current user (`/me`) with JWT
- **User dashboard**: Profile and stats for logged-in users
- **Admin dashboard**: Overview stats and recent users (admin only)
- **User management (admin)**: List, get, update, deactivate users
- **MongoDB** for all user data; passwords hashed with bcrypt
- Rate limiting on auth endpoints (OWASP-minded)
- CORS configurable for frontend

## Prerequisites

- Node.js 18+
- MongoDB (local or [MongoDB Atlas](https://www.mongodb.com/cloud/atlas))

## Setup

1. **Install dependencies**

   ```bash
   cd fraudlens-backend
   npm install
   ```

2. **Environment**

   Copy `.env.example` to `.env` and set:

   - `MONGODB_URI` – MongoDB connection string (e.g. `mongodb://localhost:27017/fraudlens`)
   - `JWT_SECRET` – Strong secret for JWT (change in production)
   - `CORS_ORIGIN` – Frontend URL (e.g. `http://localhost:3000`)

3. **Run**

   ```bash
   npm run dev
   ```

   Server runs at `http://localhost:5000` (or `PORT` in `.env`).

## API Reference

Base URL: `http://localhost:5000/api`

### Auth

| Method | Endpoint           | Body (JSON)                    | Description        |
|--------|--------------------|--------------------------------|--------------------|
| POST   | `/auth/register`   | fullName, email, phone?, password, confirmPassword | Sign up |
| POST   | `/auth/login`      | email, password                | Login, returns JWT |
| GET    | `/auth/me`         | Header: `Authorization: Bearer <token>` | Current user |

### Dashboard

| Method | Endpoint            | Auth   | Description      |
|--------|---------------------|--------|------------------|
| GET    | `/dashboard/user`   | User   | User dashboard   |
| GET    | `/dashboard/admin` | Admin  | Admin dashboard  |

### Admin – User management

All require `Authorization: Bearer <token>` and admin role.

| Method | Endpoint             | Description                    |
|--------|------------------------|--------------------------------|
| GET    | `/admin/users`        | List users (query: page, limit, search, role, isActive) |
| GET    | `/admin/users/:id`    | Get one user                  |
| PUT    | `/admin/users/:id`    | Update (fullName, phone, role, isActive) |
| DELETE | `/admin/users/:id`    | Deactivate user (soft delete) |

### Response format

- Success: `{ success: true, data: {...}, message?: "..." }`
- Error: `{ success: false, message: "..." }` (and optional `errors` for validation).

## Creating an admin user

Admins are normal users with `role: 'admin'`. After registering the first user via `/auth/register`, set admin in MongoDB:

```javascript
// In MongoDB shell or Compass
db.users.updateOne(
  { email: "admin@example.com" },
  { $set: { role: "admin" } }
)
```

Or use any script that connects to MongoDB and updates the user document.

## Frontend integration

- **Login**: `POST /api/auth/login` with `{ email, password }` → store `data.token` and `data.user`.
- **Sign up**: `POST /api/auth/register` with `{ fullName, email, phone?, password, confirmPassword }` → same as login.
- **Protected requests**: Send header `Authorization: Bearer <token>`.
- **User dashboard**: `GET /api/dashboard/user`.
- **Admin dashboard / user management**: `GET /api/dashboard/admin`, `GET/PUT/DELETE /api/admin/users` (admin only).

## License

MIT
