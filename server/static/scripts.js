let socket = null;
let currentUsername = '';
let token = null;

const messagesDiv = document.getElementById('messages');
const form = document.getElementById('chat-form');
const input = document.getElementById('message-input');

// Enable chat form
function enableChat() {
  form.style.pointerEvents = 'auto';
  form.style.opacity = '1';
}

// Decode JWT
function parseJwt(token) {
  const base64Url = token.split('.')[1];
  const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
  return JSON.parse(
    decodeURIComponent(
      atob(base64)
        .split('')
        .map((c) => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2))
        .join('')
    )
  );
}

function getTokenFromCookie(name) {
  const match = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'));
  return match ? match[2] : null;
}

// Login and connect WebSocket
const connectingOverlay = document.getElementById('connecting-overlay');

async function loginAndConnect(username, password) {
  try {
    connectingOverlay.classList.remove('hidden');

    const response = await fetch('http://localhost:8080/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({ username, password }),
    });

    if (!response.ok) throw new Error('Login failed');

    const data = await response.json();
    token = data.access_token;
    localStorage.setItem('token', token);

    const payload = parseJwt(token);
    currentUsername = payload.sub;

    socket = new WebSocket(`ws://localhost:8080/ws?token=${token}`);

    socket.addEventListener('open', () => {
      console.log('Socket connected!');
      setupSocketListeners();
      connectingOverlay.classList.add('hidden'); // Hide overlay
      enableChat();
    });

    socket.addEventListener('error', (e) => {
      console.error('WebSocket error:', e);
      connectingOverlay.innerHTML = `<div class="username-form"><h2>Connection failed. Try again.</h2></div>`;
    });
  } catch (err) {
    console.error(err);
    alert('Login failed');
    connectingOverlay.innerHTML = `<div class="username-form"><h2>Login failed</h2></div>`;
  }
}

// WebSocket event handlers
function setupSocketListeners() {
  socket.addEventListener('message', (event) => {
    try {
      const jsonData = JSON.parse(event.data);

      if (jsonData.event === 'chat_message') {
        const { user, message } = jsonData.data;

        const msgDiv = document.createElement('div');
        msgDiv.className = `message ${user}`;

        const userSpan = document.createElement('span');
        userSpan.className = 'user-name';
        userSpan.textContent = user;

        const messageSpan = document.createElement('span');
        messageSpan.className = 'message-text';
        messageSpan.textContent = message;

        msgDiv.appendChild(userSpan);
        msgDiv.appendChild(messageSpan);
        messagesDiv.appendChild(msgDiv);
        messagesDiv.scrollTop = messagesDiv.scrollHeight;
      }
    } catch (error) {
      const fallback = document.createElement('div');
      fallback.className = 'message bot';
      fallback.textContent = event.data;
      messagesDiv.appendChild(fallback);
      messagesDiv.scrollTop = messagesDiv.scrollHeight;
    }
  });
}

window.addEventListener('DOMContentLoaded', () => {
  token = getTokenFromCookie('access_token');
  if (!token) {
    window.location.href = '/login';
    return;
  }

  try {
    const payload = parseJwt(token);
    currentUsername = payload.sub;
  } catch (err) {
    console.error('Invalid token');
    window.location.href = '/login';
    return;
  }

  connectingOverlay?.classList.remove('hidden');
  socket = new WebSocket(`ws://localhost:8080/ws?token=${token}`);

  socket.addEventListener('open', () => {
    console.log('Socket connected!');
    setupSocketListeners();
    enableChat();
    connectingOverlay?.classList.add('hidden');
  });

  socket.addEventListener('error', (e) => {
    console.error('WebSocket error:', e);
    connectingOverlay.innerHTML = `<div class="username-form"><h2>Connection failed. Try again.</h2></div>`;
  });
});

form.addEventListener('submit', (e) => {
  e.preventDefault();

  if (!socket || socket.readyState !== WebSocket.OPEN) {
    console.warn('Socket is not connected.');
    return;
  }

  if (input.value.trim() !== '' && currentUsername) {
    const message = {
      event: 'chat_message',
      data: {
        user: currentUsername,
        message: input.value,
      },
    };
    socket.send(JSON.stringify(message));
    input.value = '';
  }
});


document.getElementById('logout-btn').addEventListener('click', () => {
  localStorage.removeItem('token');             // Clear token
  document.cookie = 'access_token=; Max-Age=0'; // Optional: clear cookie too
  window.location.href = '/login';              // Redirect to login
});
