![Chat App Demo](assets/readme.gif)

# 🗨️ FastAPI WebSocket Chat App

A modern real-time chat application built with **FastAPI**, **WebSockets**, **SQLite**, and **vanilla JS**, with full authentication and dynamic user interactions.

## 🚀 Features

### ✅ Authentication
- **Login & Registration** via a secure token-based system (JWT)
- **Session persistence** via HTTP-only cookies
- Redirects unauthenticated users to the login page automatically

### ✅ Password Encryption
- User passwords are **securely hashed** using **Bcrypt** via the `passlib` library
- A **unique salt** is automatically generated and embedded in each hash
- Plain-text passwords are never stored or logged
- Passwords are verified using a constant-time comparison to prevent timing attacks

### ✅ Asymmetrically Encrypted PMs between Users using RSA-OAEP
- Each user generates a **public/private key pair** upon connection  
- Public keys are shared with other users through the server  
- **End-to-end encryption** is enforced by encrypting messages with the recipient's public key  
- Only the intended recipient can decrypt messages using their **private key**  
- The server only relays encrypted content and cannot decrypt or inspect private messages  

### 🧑‍💻 Real-Time Chat
- WebSocket-based messaging with instant updates
- Dynamic user join/leave events
- Server-side broadcasting to all connected clients
- Message validation and serialization powered by **Pydantic**
- Login & registration pages styled for clarity and feedback
- Chat interface with message input and scrollable message history

### 🔐 Token Handling
- JWT tokens stored as cookies and validated on every request
- WebSocket connections require a valid token as a query parameter

### 🔧 Modular Codebase
- `auth/`, `chat/`, `pages/` routes separated by concern
- `utils/template_engine.py` for centralized Jinja2 rendering
- `dbmodels.py` and `db.py` for clean database access

### 🛠️ Tech Stack
- **FastAPI** – backend framework
- **WebSockets** – for real-time communication
- **Pydantic** – data validation and structured serialization
- **SQLite** – lightweight embedded database
- **SQLAlchemy** – ORM for database operations
- **Jinja2** – HTML template rendering
- **Passlib + Bcrypt** – password hashing
- **Vanilla JS** – lightweight client-side interactivity


## 🏃‍♂️ Running the App

from root repo folder.

```
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
uvicorn server.main:app --host localhost --port 8080
```
