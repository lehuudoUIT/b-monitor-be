# Traffic Anomaly Detection Backend

A FastAPI-based backend system for traffic monitoring and anomaly detection with JWT authentication.

## Features

- **Clean Architecture**: Organized with routers, models, schemas, and services
- **JWT Authentication**: Secure stateless authentication with Bearer tokens
- **Async SQLAlchemy**: Asynchronous database operations with SQLite
- **CORS Enabled**: Configured for React frontend integration
- **Type Safety**: Pydantic schemas for request/response validation
- **Password Hashing**: Bcrypt-based secure password storage

## Project Structure

```
b-monitor-be/
├── app/
│   ├── core/
│   │   ├── __init__.py
│   │   ├── database.py       # Database configuration
│   │   ├── auth.py          # JWT & password utilities
│   │   └── dependencies.py   # Auth dependencies
│   ├── models/
│   │   ├── __init__.py
│   │   └── models.py         # SQLAlchemy models
│   ├── schemas/
│   │   ├── __init__.py
│   │   └── schemas.py        # Pydantic schemas
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── auth.py          # Authentication endpoints
│   │   └── users.py         # User endpoints
│   ├── services/
│   │   ├── __init__.py
│   │   └── user_service.py  # User business logic
│   └── __init__.py
├── main.py                   # FastAPI application entry point
├── requirements.txt          # Python dependencies
├── .env.example             # Environment variables template
├── setup.bat / setup.sh     # Automated setup scripts
├── test_auth.py             # Authentication test script
├── AUTH_README.md           # Authentication documentation
└── .gitignore
```

## Database Schema

### Tables

1. **User**

   - id (Primary Key)
   - username (unique)
   - email (unique)
   - password (hashed)
   - created_at, updated_at

2. **Camera**

   - id (Primary Key)
   - name, location, thumbnail
   - status, url
   - type (enum: local, youtube)
   - user_id (Foreign Key → User)
   - created_at, updated_at

3. **NormalFeature**

   - id (Primary Key)
   - cam_id (Foreign Key → Camera)
   - url (path to feature file)
   - created_at, updated_at

4. **Anomaly**
   - id (Primary Key)
   - time, type, description
   - level (enum: violations, critical, high, medium, low)
   - cam_id (Foreign Key → Camera)
   - created_at, updated_at

## Setup Instructions

### Quick Setup (Recommended)

**Windows:**

```bash
setup.bat
```

**Linux/Mac:**

```bash
chmod +x setup.sh
./setup.sh
```

### Manual Setup

### 1. Create Virtual Environment

```bash
python -m venv venv
```

### 2. Activate Virtual Environment

**Windows:**

```bash
venv\Scripts\activate
```

**Linux/Mac:**

```bash
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment

```bash
# Copy the example environment file
copy .env.example .env

# Edit .env file with your configuration
```

### 5. Run the Application

- Step 1:

```bash
venv\Scripts\activate
```

- Step 2:

```bash
uvicorn main:app --reload
```

The API will be available at: `http://localhost:8000`

### 6. Test Authentication

```bash
# Install requests library for testing
pip install requests

# Run test script
python test_auth.py
```

## Authentication

The API uses JWT (JSON Web Tokens) for authentication. See [AUTH_README.md](AUTH_README.md) for detailed documentation.

### Quick Start

1. **Register a user:**

```bash
POST /auth/register
{
  "username": "john_doe",
  "email": "john@example.com",
  "password": "securepass123"
}
```

2. **Login to get token:**

```bash
POST /auth/login
{
  "username": "john_doe",
  "password": "securepass123"
}
```

3. **Use token in requests:**

```bash
GET /users/me
Headers: Authorization: Bearer {your_token}
```

### Protected Routes

To protect any endpoint, use the `CurrentUser` dependency:

```python
from app.core.dependencies import CurrentUser

@router.get("/my-endpoint")
async def my_endpoint(current_user: CurrentUser):
    return {"user_id": current_user.id}
```

## API Documentation

Once running, visit:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## Next Steps

1. **Implement Routers**: Create API endpoints in `app/routers/`
2. **Add Services**: Implement business logic in `app/services/`
3. **Authentication**: Add JWT-based authentication for users
4. **Testing**: Write unit and integration tests
5. **Logging**: Add comprehensive logging
6. **Deployment**: Configure for production deployment

## Development

### Adding New Endpoints

1. Create a new router file in `app/routers/`
2. Define endpoints using FastAPI decorators
3. Import and include router in `main.py`

### Database Migrations

For production, consider using Alembic for database migrations:

```bash
pip install alembic
alembic init migrations
```

Migration:

```bash
alembic revision --autogenerate -m "Add fps and resolution column to table camera"
alembic upgrade head
```

## License

[Your License Here]
