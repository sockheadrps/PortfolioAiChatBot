let socket = new WebSocket('ws://localhost:8080/ws');
let currentUsername = '';

const messagesDiv = document.getElementById('messages');
const form = document.getElementById('chat-form');
const input = document.getElementById('message-input');
const usernameOverlay = document.getElementById('username-overlay');
const usernameInput = document.getElementById('username-input');
const enterBtn = document.getElementById('enter-btn');

// Disable chat form until username is entered
form.style.pointerEvents = 'none';
form.style.opacity = '0.5';

// Username handling
function handleUsernameEnter() {
  const username = usernameInput.value.trim();
  if (username.length >= 2) {
    currentUsername = username;
    usernameOverlay.classList.add('hidden');
    enableChat();
    input.focus();

    // Add chat-ready class to fade in chat interface
    document.getElementById('chat-container').classList.add('chat-ready');

    // Send message to parent window (if in iframe)
    if (window.parent !== window) {
      try {
        window.parent.postMessage(
          JSON.stringify({
            event: 'username_entered',
            username: username,
          }),
          '*'
        );
      } catch (e) {
        console.log('Could not send message to parent window');
      }
    }

    // Add welcome message
    const welcomeMsg = document.createElement('div');
    welcomeMsg.className = 'message bot';
    welcomeMsg.innerHTML = `
            <span class="user-name">System</span>
            <span class="message-text">Welcome, ${username}! You can now start chatting.</span>
        `;
    messagesDiv.appendChild(welcomeMsg);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
  } else {
    usernameInput.style.borderColor = 'rgba(255, 100, 100, 0.8)';
    usernameInput.style.boxShadow = '0 0 15px rgba(255, 100, 100, 0.3)';
    setTimeout(() => {
      usernameInput.style.borderColor = 'rgba(255, 255, 255, 0.3)';
      usernameInput.style.boxShadow = 'none';
    }, 2000);
  }
}

enterBtn.addEventListener('click', handleUsernameEnter);

usernameInput.addEventListener('keypress', (e) => {
  if (e.key === 'Enter') {
    handleUsernameEnter();
  }
});

// Enable chat form when username is entered
function enableChat() {
  form.style.pointerEvents = 'auto';
  form.style.opacity = '1';
}

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
      userSpan.style.fontWeight = 'bold';
      userSpan.style.fontSize = '12px';
      userSpan.style.opacity = '0.8';
      userSpan.style.marginBottom = '4px';
      userSpan.style.display = 'block';

      const messageSpan = document.createElement('span');
      messageSpan.className = 'message-text';
      messageSpan.textContent = message;

      msgDiv.appendChild(userSpan);
      msgDiv.appendChild(messageSpan);

      messagesDiv.appendChild(msgDiv);
      messagesDiv.scrollTop = messagesDiv.scrollHeight;
    }
  } catch (error) {
    console.error('Error parsing message:', error);
    // Fallback for non-JSON messages
    const msg = document.createElement('div');
    msg.className = 'message bot';
    msg.textContent = event.data;
    messagesDiv.appendChild(msg);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
  }
});

form.addEventListener('submit', (e) => {
  e.preventDefault();
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
