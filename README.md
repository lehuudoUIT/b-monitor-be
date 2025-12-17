# Traffic Anomaly Detection Backend

A FastAPI-based backend system for traffic monitoring and anomaly detection.

## Features

- **Clean Architecture**: Organized with routers, models, schemas, and services
- **Async SQLAlchemy**: Asynchronous database operations with SQLite
- **CORS Enabled**: Configured for React frontend integration
- **Type Safety**: Pydantic schemas for request/response validation

## Project Structure

```
b-monitor-be/
├── app/
│   ├── core/
│   │   ├── __init__.py
│   │   └── database.py       # Database configuration
│   ├── models/
│   │   ├── __init__.py
│   │   └── models.py         # SQLAlchemy models
│   ├── schemas/
│   │   ├── __init__.py
│   │   └── schemas.py        # Pydantic schemas
│   ├── routers/              # API endpoints (to be implemented)
│   ├── services/             # Business logic (to be implemented)
│   └── __init__.py
├── main.py                   # FastAPI application entry point
├── requirements.txt          # Python dependencies
├── .env.example             # Environment variables template
└── .gitignore
```

## Database Schema

### Tables

1. **User**

   - id (Primary Key)
   - username (unique)
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

```bash
uvicorn main:app --reload
```

The API will be available at: `http://localhost:8000`

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

## License

[Your License Here]
