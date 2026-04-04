# Flask Backend – Phase 1 (Auth + Wallet Linking)

## Folder Structure

```
flask_backend/
├── app.py                        # Entry point – Flask application factory
├── config.py                     # Configuration (SECRET_KEY, DEBUG)
├── db.py                         # SQLite connection helpers & init
├── schema.sql                    # SQL DDL for users & wallets tables
├── requirements.txt              # Python dependencies
├── .env.example                  # Environment variable template
│
├── models/
│   ├── user.py                   # User CRUD helpers
│   └── wallet.py                 # Wallet CRUD helpers
│
├── routes/
│   ├── auth_routes.py            # POST /register, POST /login
│   └── wallet_routes.py          # POST /wallets, GET /wallets
│
├── services/
│   ├── auth_service.py           # Registration & login logic, JWT
│   └── wallet_service.py         # Wallet linking & validation logic
│
├── middleware/
│   └── auth_middleware.py        # @token_required, @admin_required decorators
│
└── postman/
    └── collection.json           # Importable Postman collection
```

## Quick Start

### 1. Create & activate a virtual environment

```bash
cd flask_backend
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Run the server

```bash
python app.py
```

The API starts at **http://localhost:5000**.  
The database file `fraud_detection.db` is auto-created on first run.

### 4. Verify

```
GET http://localhost:5000/api/health
→ { "status": "ok", "message": "API is running." }
```

---

## API Endpoints

| Method | Endpoint             | Auth?  | Description           |
| ------ | -------------------- | ------ | --------------------- |
| POST   | `/api/auth/register` | No     | Register a new user   |
| POST   | `/api/auth/login`    | No     | Login, get JWT token  |
| POST   | `/api/wallets`       | Bearer | Link a wallet to user |
| GET    | `/api/wallets`       | Bearer | List user's wallets   |
| GET    | `/api/health`        | No     | Health check          |

### Register

```json
POST /api/auth/register
Content-Type: application/json

{
  "full_name": "Kofi Mensah",
  "email": "kofi@example.com",
  "phone_number": "0241234567",
  "password": "securePass123",
  "role": "customer"
}
```

### Login

```json
POST /api/auth/login
Content-Type: application/json

{
  "email": "kofi@example.com",
  "password": "securePass123"
}
```

### Add Wallet (requires token)

```json
POST /api/wallets
Authorization: Bearer <your_token>
Content-Type: application/json

{
  "wallet_number": "0241234567",
  "provider": "MTN",
  "wallet_name": "My MTN MoMo",
  "is_primary": true
}
```

### List Wallets (requires token)

```
GET /api/wallets
Authorization: Bearer <your_token>
```

---

## Notes

- Passwords are hashed with **bcrypt** – never stored in plain text.
- JWTs expire after **24 hours**.
- The `provider` field only accepts: `MTN`, `Telecel`, `AirtelTigo`.
- Duplicate wallet numbers (same number + provider) are rejected automatically.
- To switch to PostgreSQL later, replace the SQLite connection in `db.py` with `psycopg2` or SQLAlchemy.
