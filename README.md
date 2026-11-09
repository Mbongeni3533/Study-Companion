# Study Companion App

An AI-powered study helper that works with lecturers to help students study smarter.

## Project Structure

```
study-companion-app/
├── backend/           # FastAPI backend
│   ├── app/
│   │   ├── models.py          # Database models
│   │   ├── schemas.py         # Pydantic schemas
│   │   ├── database.py        # Database configuration
│   │   ├── routes/            # API routes
│   │   │   ├── auth.py        # Authentication endpoints
│   │   │   └── documents.py   # Document management
│   │   └── services/
│   │       └── document_processor.py
│   ├── main.py              # Main FastAPI app
│   ├── requirements.txt
│   └── start.sh             # Development server script
├── frontend/           # React Native mobile app
│   └── src/
│       └── components/
│           └── App.js
└── README.md
```

## Quick Start

### Backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# or: .\venv\Scripts\activate on Windows

pip install -r requirements.txt
python main.py
```

The API will be available at `http://localhost:8000`

API Endpoints:
- `POST /auth/register` - Register a new user
- `POST /auth/login` - Login
- `POST /auth/anonymous-session` - Start as anonymous user
- `POST /documents/courses` - Create a course
- `POST /documents/courses/{id}/documents` - Upload document
- `GET /documents/courses/{id}/documents` - List documents
- `GET /documents/courses/{id}/topics` - Get topic map
- `DELETE /documents/courses/{id}/documents/{doc_id}` - Delete document

### Frontend

```bash
cd frontend
npm install
npm start
```

## Development Status

### Phase 1: MVP Core (In Progress)
- [x] User authentication (register/login)
- [x] Anonymous session support
- [x] Course management
- [x] Document upload pipeline
- [ ] File parsing (PDF, DOCX, PPTX, images)
- [ ] Text chunking
- [ ] Topic mapping
- [ ] AI Study Coach integration

### Phase 2: AI Features
- [ ] Task generation
- [ ] Chat with AI coach
- [ ] Progress tracking
- [ ] Exam readiness assessment

### Phase 3: Production
- [ ] Payment integration
- [ ] Offline mode
- [ ] Mobile app (iOS/Android)
- [ ] Institution licensing

## Key Features

1. **Teacher-First Design**: Works with existing course materials
2. **No Spoon-Feeding**: Graduated hint system encourages learning
3. **Privacy by Design**: Student data stays private
4. **Adaptive Learning**: Adjusts to student's capacity
5. **Offline Support**: Study without internet

## Database Models

- **User**: Accounts, profiles, subscription status
- **Course**: Subject, code, exam dates
- **Document**: Uploaded files with status tracking
- **Chunk**: Text segments with embeddings
- **Topic**: Learning topics and outcomes
- **Task**: Generated study tasks
- **ChatSession/Message**: AI conversation history

## Technology Stack

- **Backend**: FastAPI (Python), PostgreSQL/SQLite, JWT auth
- **Frontend**: React Native, Expo
- **AI**: Claude/PaLM API (to be integrated)
- **Storage**: S3-compatible (local MinIO for dev)

## Contributing

1. Fork the repository
2. Create your feature branch
3. Commit your changes
4. Push to the branch
5. Open a pull request

## License

This project is proprietary. All rights reserved.