// State management
let socket = null;
let currentUsername = '';
let token = null;
let keyPair = null;
let userPublicKeys = new Map();

// DOM elements
const elements = {
  messages: document.getElementById('messages'),
  form: document.getElementById('chat-form'),
  input: document.getElementById('message-input'),
  onlineUsers: document.getElementById('online-users'),
  connectingOverlay: document.getElementById('connecting-overlay'),
  logoutBtn: document.getElementById('logout-btn'),
  privateChatContainer: document.getElementById('private-chat-container'),
  privateChatBox: document.getElementById('private-chat-box'),
  privateChatClose: document.getElementById('close-private-chat'),
  privateChatMinimize: document.getElementById('minimize-private-chat'),
  privateChatDisconnect: document.getElementById('disconnect-private-chat'),
  privateInput: document.getElementById('private-input'),
  privateSendBtn: document.getElementById('private-send-btn'),
  privateChatFooter: document.getElementById('private-chat-footer'),
  usersToggle: document.getElementById('users-toggle'),
  usersPanel: document.getElementById('users-panel'),
  mainContainer: document.querySelector('.main-container'),
};

// Utility functions
const utils = {
  parseJwt: (token) => {
    try {
      return JSON.parse(atob(token.split('.')[1]));
    } catch {
      return null;
    }
  },

  getTokenFromCookie: (name) => {
    const match = document.cookie.match(new RegExp(`(^| )${name}=([^;]+)`));
    return match ? match[2] : null;
  },

  createElement: (tag, className, textContent = '') => {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (textContent) element.textContent = textContent;
    return element;
  },

  scrollToBottom: (element) => {
    element.scrollTop = element.scrollHeight;
  },

  // Check if Web Crypto API is available
  isCryptoAvailable: () => {
    return (
      window.crypto &&
      window.crypto.subtle &&
      typeof window.crypto.subtle.generateKey === 'function'
    );
  },

  // RSA Encryption functions
  generateKeyPair: async () => {
    if (!utils.isCryptoAvailable()) {
      throw new Error(
        'Web Crypto API is not available. Private messages require HTTPS or localhost.'
      );
    }

    keyPair = await window.crypto.subtle.generateKey(
      {
        name: 'RSA-OAEP',
        modulusLength: 2048,
        publicExponent: new Uint8Array([1, 0, 1]),
        hash: 'SHA-256',
      },
      true,
      ['encrypt', 'decrypt']
    );
    console.log('RSA key pair generated successfully');
    return keyPair;
  },

  exportPublicKey: async (publicKey) => {
    if (!utils.isCryptoAvailable()) {
      throw new Error('Web Crypto API is not available');
    }
    if (!publicKey) {
      throw new Error('No public key provided');
    }
    const exported = await window.crypto.subtle.exportKey('spki', publicKey);
    const exportedAsString = utils.arrayBufferToBase64(exported);
    return exportedAsString;
  },

  importPublicKey: async (publicKeyString) => {
    if (!utils.isCryptoAvailable()) {
      throw new Error('Web Crypto API is not available');
    }
    if (!publicKeyString) {
      throw new Error('No public key string provided');
    }
    const publicKeyBuffer = utils.base64ToArrayBuffer(publicKeyString);
    const publicKey = await window.crypto.subtle.importKey(
      'spki',
      publicKeyBuffer,
      { name: 'RSA-OAEP', hash: 'SHA-256' },
      true,
      ['encrypt']
    );
    return publicKey;
  },

  encrypt: async (message, recipientUsername) => {
    if (!utils.isCryptoAvailable()) {
      throw new Error(
        'Web Crypto API is not available. Private messages require HTTPS or localhost.'
      );
    }

    if (!keyPair) {
      throw new Error('No key pair available for encryption');
    }

    if (!userPublicKeys.has(recipientUsername)) {
      throw new Error(`No public key found for ${recipientUsername}`);
    }

    const publicKey = userPublicKeys.get(recipientUsername);
    if (!publicKey) {
      throw new Error(`Invalid public key for ${recipientUsername}`);
    }

    const encodedMessage = new TextEncoder().encode(message);
    const encrypted = await window.crypto.subtle.encrypt(
      { name: 'RSA-OAEP' },
      publicKey,
      encodedMessage
    );

    return utils.arrayBufferToBase64(encrypted);
  },

  decrypt: async (ciphertext) => {
    if (!utils.isCryptoAvailable()) {
      throw new Error('Web Crypto API is not available. Cannot decrypt private messages.');
    }

    if (!keyPair) {
      throw new Error('No key pair available for decryption');
    }

    const encryptedBuffer = utils.base64ToArrayBuffer(ciphertext);
    const decrypted = await window.crypto.subtle.decrypt(
      { name: 'RSA-OAEP' },
      keyPair.privateKey,
      encryptedBuffer
    );

    return new TextDecoder().decode(decrypted);
  },

  // Helper functions for base64 conversion
  arrayBufferToBase64: (buffer) => {
    let binary = '';
    const bytes = new Uint8Array(buffer);
    const len = bytes.byteLength;
    for (let i = 0; i < len; i++) {
      binary += String.fromCharCode(bytes[i]);
    }
    return btoa(binary);
  },

  base64ToArrayBuffer: (base64) => {
    const binaryString = atob(base64);
    const len = binaryString.length;
    const bytes = new Uint8Array(len);
    for (let i = 0; i < len; i++) {
      bytes[i] = binaryString.charCodeAt(i);
    }
    return bytes.buffer;
  },
};

// Message handling
const messageHandler = {
  addMessage: (container, user, message, className = '') => {
    const msgDiv = utils.createElement('div', `message ${className}`);
    msgDiv.innerHTML = `
      <span class="user-name">${user}</span>
      <span class="message-text">${message}</span>
    `;
    container.appendChild(msgDiv);
    utils.scrollToBottom(container);
  },

  addSystemMessage: (container, message) => {
    const msgDiv = utils.createElement('div', 'message system');
    msgDiv.innerHTML = message;
    container.appendChild(msgDiv);
    utils.scrollToBottom(container);
  },
};

// WebSocket message handlers
const socketHandlers = {
  chat_message: (data) => {
    if (elements.messages) {
      messageHandler.addMessage(elements.messages, data.user, data.message);
    } else {
      console.error('Messages element not found!');
    }
  },

  user_list: (data) => {
    if (!elements.onlineUsers) return;
    elements.onlineUsers.innerHTML = '';

    data.users
      .filter((user) => user !== currentUsername)
      .forEach((user, index) => {
        const li = utils.createElement('li', 'online-user');
        li.innerHTML = `
          <span class="user-name">${user}</span>
          <button class="pm-button" onclick="sendPmInvite('${user}')">PM</button>
        `;

        // If panel is visible, add staggered animation
        if (!isPanelHidden) {
          li.style.animationDelay = `${0.4 + index * 0.1}s`;
        }

        elements.onlineUsers.appendChild(li);
      });
  },

  pm_message: async (data) => {
    try {
      const decryptedMessage = await utils.decrypt(data.ciphertext);
      messageHandler.addMessage(elements.privateChatBox, data.from, decryptedMessage);
      openPrivateChat(data.from);
    } catch (error) {
      console.error('Error handling PM message:', error);
      messageHandler.addMessage(
        elements.privateChatBox,
        data.from,
        '[Encrypted message - decryption failed]'
      );
    }
  },

  pubkey_request: (data) => {
    // Someone is requesting our public key
    sendPublicKey(data.from);
  },

  pubkey_response: async (data) => {
    // Received someone's public key
    try {
      const publicKey = await utils.importPublicKey(data.public_key);
      userPublicKeys.set(data.from, publicKey);
      console.log(`Stored public key for ${data.from}`);
    } catch (error) {
      console.error(`Error storing public key for ${data.from}:`, error);
    }
  },

  pm_invite: (data) => {
    showPmInviteToast(data.from);
  },

  pm_accept: (data) => {
    const fromUser = data.from;
    ensurePmFooterTab(fromUser, fromUser, 'accepted');
    messageHandler.addSystemMessage(
      elements.privateChatBox,
      `${fromUser} accepted the private chat.`
    );
    openPrivateChat(fromUser);
  },

  pm_decline: (data) => {
    const fromUser = data.from;
    ensurePmFooterTab(fromUser, fromUser, 'declined');
    messageHandler.addSystemMessage(
      elements.messages,
      'System',
      `${fromUser} declined your private chat request.`
    );
  },

  pm_disconnect: (data) => {
    const fromUser = data.from;

    ensurePmFooterTab(fromUser, fromUser, 'disconnected');

    if (currentPmUser === fromUser) {
      messageHandler.addSystemMessage(
        elements.privateChatBox,
        `${fromUser} has disconnected from the private chat.`
      );

      setPrivateChatEnabled(false);
      elements.privateChatMinimize.style.display = 'none';
      elements.privateChatDisconnect.style.display = 'none';
      elements.privateChatClose.style.display = 'inline-block'; // make sure Close is visible
    } else {
      messageHandler.addSystemMessage(
        elements.messages,
        'System',
        `${fromUser} has disconnected from your private chat.`
      );
    }
  },
};

// WebSocket setup
function setupSocket() {
  socket = new WebSocket(`ws://chat.socksthoughtshop.lol:8118/ws?token=${token}`);

  socket.addEventListener('open', () => {
    elements.form.style.pointerEvents = 'auto';
    elements.form.style.opacity = '1';
    elements.connectingOverlay?.classList.add('hidden');
  });

  socket.addEventListener('message', (event) => {
    try {
      const data = JSON.parse(event.data);

      const handler = socketHandlers[data.event] || socketHandlers[data.type];
      if (handler) {
        handler(data.data || data);
      } else {
        // Try to handle as a fallback message
        if (typeof data === 'string') {
          messageHandler.addMessage(elements.messages, 'System', data, 'bot');
        }
      }
    } catch (error) {
      console.error('Error parsing WebSocket message:', error);
      console.log('Raw message that failed to parse:', event.data);

      // Handle non-JSON messages (like "Unknown message type")
      if (typeof event.data === 'string') {
        messageHandler.addMessage(elements.messages, 'System', event.data, 'bot');
      }
    }
  });

  socket.addEventListener('error', () => {
    elements.connectingOverlay.innerHTML =
      '<div class="username-form"><h2>Connection failed. Try again.</h2></div>';
  });
}

function updateOnlineUsers(userList) {
  if (!elements.onlineUsers) return;
  elements.onlineUsers.innerHTML = '';

  userList.forEach((user) => {
    if (user !== currentUsername) {
      const li = utils.createElement('li', 'online-user');
      li.innerHTML = `
        <span class="user-name">${user}</span>
        <button class="pm-button" onclick="sendPmInvite('${user}')">PM</button>
      `;
      elements.onlineUsers.appendChild(li);
    }
  });
}

// Private chat functions
function showPmInviteToast(fromUser) {
  const toastContainer = document.getElementById('invite-toast-container');
  const toast = utils.createElement('div', 'invite-toast');

  toast.innerHTML = `
    <span><b>${fromUser}</b> invited you to a private chat</span>
    <button onclick="acceptPmInvite('${fromUser}', this.parentElement)">Accept</button>
    <button onclick="declinePmInvite('${fromUser}', this.parentElement)">Decline</button>
  `;

  toastContainer.appendChild(toast);
  setTimeout(() => toast.remove(), 15000);
}

function declinePmInvite(user, toast) {
  socket.send(JSON.stringify({ type: 'pm_decline', to: user }));
  toast.remove();
}

function sendPmInvite(user) {
  ensurePmFooterTab(user, user, 'pending');
  socket.send(JSON.stringify({ type: 'pm_invite', to: user }));
  // Request the user's public key for encryption
  requestPublicKey(user);
}

async function requestPublicKey(username) {
  socket.send(
    JSON.stringify({
      type: 'pubkey_request',
      to: username,
    })
  );
}

async function sendPublicKey(username) {
  try {
    if (!utils.isCryptoAvailable() || !keyPair) {
      throw new Error('Cannot send public key - crypto not available or no key pair');
    }

    const publicKeyString = await utils.exportPublicKey(keyPair.publicKey);
    socket.send(
      JSON.stringify({
        type: 'pubkey_response',
        to: username,
        public_key: publicKeyString,
      })
    );
    console.log(`Sent public key to ${username}`);
  } catch (error) {
    console.error(`Error sending public key to ${username}:`, error);
  }
}

function acceptPmInvite(user, toast) {
  socket.send(JSON.stringify({ type: 'pm_accept', to: user }));
  ensurePmFooterTab(user, user, 'accepted');
  openPrivateChat(user);
  toast.remove();
  // Request the user's public key for encryption
  requestPublicKey(user);
}

function openPrivateChat(user) {
  currentPmUser = user;
  elements.privateChatContainer.style.display = 'flex';
  elements.privateChatContainer.classList.remove('hidden');
  elements.privateChatContainer.dataset.user = user;

  // Update the chat header with the user's name
  const chatUserName = document.getElementById('chat-user-name');
  if (chatUserName) {
    chatUserName.textContent = `with ${user}`;
  }

  elements.privateChatMinimize.style.display = 'inline-block';
  elements.privateChatDisconnect.style.display = 'inline-block';
  elements.privateChatClose.style.display = 'inline-block';

  elements.privateChatBox.innerHTML = '';

  const messages = pmSessions.get(user) || [];
  if (messages.length === 0) {
    messageHandler.addSystemMessage(
      elements.privateChatBox,
      `Private chat with <b>${user}</b> started.`
    );
  } else {
    messages.forEach(({ from, text }) => {
      messageHandler.addMessage(elements.privateChatBox, from, text);
    });
  }

  activateTab(user);

  const tab = document.getElementById(`pm-tab-${user}`);
  if (tab?.classList.contains('disconnected')) {
    setPrivateChatEnabled(false);
    elements.privateChatMinimize.style.display = 'none';
    elements.privateChatDisconnect.style.display = 'none';
  } else {
    setPrivateChatEnabled(true);
  }
}

async function sendPrivateMessage() {
  const msg = elements.privateInput.value.trim();
  const to = elements.privateChatContainer.dataset.user;

  if (msg && to) {
    try {
      const ciphertext = await utils.encrypt(msg, to);
      socket.send(
        JSON.stringify({
          type: 'pm_message',
          to,
          ciphertext,
        })
      );
      messageHandler.addMessage(elements.privateChatBox, currentUsername, msg);
      elements.privateInput.value = '';
    } catch (error) {
      console.error('Error sending private message:', error);
      messageHandler.addSystemMessage(
        elements.privateChatBox,
        'Failed to encrypt and send message. Please try again.'
      );
    }
  }
}

function closePrivateChat() {
  const user = elements.privateChatContainer.dataset.user;
  elements.privateChatContainer.style.display = 'none';
  elements.privateChatBox.innerHTML = '';
  delete elements.privateChatContainer.dataset.user;

  // Clear the username from header
  const chatUserName = document.getElementById('chat-user-name');
  if (chatUserName) {
    chatUserName.textContent = '';
  }

  // If the user was marked as disconnected, remove the tab entirely
  const tab = document.getElementById(`pm-tab-${user}`);
  if (tab?.classList.contains('disconnected')) {
    tab.remove();
    pmSessions.delete(user);
    currentPmUser = null;
  }
}

function minimizePrivateChat() {
  elements.privateChatContainer.classList.add('hidden');

  // Clear the username from header when minimized
  const chatUserName = document.getElementById('chat-user-name');
  if (chatUserName) {
    chatUserName.textContent = '';
  }
}

function setPrivateChatEnabled(enabled) {
  elements.privateInput.disabled = !enabled;
  elements.privateSendBtn.disabled = !enabled;

  elements.privateInput.placeholder = enabled
    ? 'Type a private message...'
    : 'Private chat disconnected';
}

function disconnectPrivateChat() {
  const currentUser = elements.privateChatContainer.dataset.user;
  if (currentUser) {
    // Send disconnect notification to the other user
    socket.send(
      JSON.stringify({
        type: 'pm_disconnect',
        to: currentUser,
      })
    );

    // Remove the tab
    const tab = document.getElementById(`pm-tab-${currentUser}`);
    if (tab) {
      tab.remove();
    }

    // Clear the session
    pmSessions.delete(currentUser);

    messageHandler.addSystemMessage(
      elements.privateChatBox,
      `You have disconnected the private chat.`
    );

    // Close the chat window
    closePrivateChat();

    // Reset current user if it was the active one
    if (currentPmUser === currentUser) {
      currentPmUser = null;
    }
    setPrivateChatEnabled(false);
  }
}

// Handle Enter key in private chat input
function handlePrivateInputKeyPress(event) {
  if (event.key === 'Enter') {
    event.preventDefault();
    sendPrivateMessage();
  }
}

// PM Session Management
const pmSessions = new Map(); // key: username, value: array of messages
let currentPmUser = null;

// Add footer tab if it doesn't exist
// Ensure a private message footer tab for a given user/conversation
function ensurePmFooterTab(chatId, userName, status) {
  const footer = document.getElementById('pm-footer'); // Container for PM tabs
  if (!footer) return; // Footer container must exist

  const tabId = `pm-tab-${chatId}`; // Unique ID for the tab element
  let tab = document.getElementById(tabId);

  // If the tab doesn't exist yet, create it
  if (!tab && status !== 'declined') {
    tab = document.createElement('div');
    tab.id = tabId;
    tab.classList.add('pm-tab');

    // Apply status-specific styling via classes
    if (status === 'pending') {
      tab.classList.add('pending');
      tab.textContent = `${userName} (pending)`;
    } else if (status === 'accepted') {
      tab.classList.add('accepted');
      tab.textContent = userName;
    } else if (status === 'disconnected') {
      tab.classList.add('disconnected');
      tab.textContent = `${userName} (offline)`;
    }

    // Click handler for toggling the private chat window
    tab.addEventListener('click', function () {
      // Toggle visibility: show/hide the chat window
      if (elements.privateChatContainer.classList.contains('hidden')) {
        // Show the chat window
        elements.privateChatContainer.classList.remove('hidden');
        switchToPmChat(chatId);
      } else {
        // Hide the chat window
        elements.privateChatContainer.classList.add('hidden');
      }

      // Toggle active class on all tabs
      document.querySelectorAll('.pm-tab').forEach((t) => t.classList.remove('active'));
      if (!elements.privateChatContainer.classList.contains('hidden')) {
        tab.classList.add('active');
      }
    });

    footer.appendChild(tab);
  } else if (tab) {
    // Tab already exists: update its status styling if needed
    if (!tab.classList.contains('disconnected')) {
      tab.classList.remove('pending', 'accepted'); // don't remove disconnected if it's already there
    }

    if (status === 'pending') {
      tab.classList.add('pending');
      tab.textContent = `${userName} (pending)`;
    } else if (status === 'accepted') {
      tab.classList.add('accepted');
      tab.textContent = userName;
    } else if (status === 'disconnected') {
      tab.classList.add('disconnected');
      tab.textContent = `${userName} (offline)`;
    }
  }

  // If status is 'declined', remove the tab from the footer
  if (status === 'declined' && tab) {
    footer.removeChild(tab);
  }
}

// Switch to PM with given user
function switchToPmChat(user) {
  currentPmUser = user;
  elements.privateChatContainer.dataset.user = user;

  // Update the chat header with the user's name
  const chatUserName = document.getElementById('chat-user-name');
  if (chatUserName) {
    chatUserName.textContent = `with ${user}`;
  }

  // Activate the clicked tab
  document.querySelectorAll('.pm-tab').forEach((btn) => btn.classList.remove('active'));
  document.getElementById(`pm-tab-${user}`)?.classList.add('active');

  // Display chat
  elements.privateChatContainer.style.display = 'flex';
  elements.privateChatContainer.classList.remove('hidden');

  const messages = pmSessions.get(user) || [];
  elements.privateChatBox.innerHTML = '';

  if (messages.length === 0) {
    messageHandler.addSystemMessage(
      elements.privateChatBox,
      `Private chat with <b>${user}</b> started.`
    );
  } else {
    messages.forEach(({ from, text }) => {
      messageHandler.addMessage(elements.privateChatBox, from, text);
    });
  }
  if (document.getElementById(`pm-tab-${user}`)?.classList.contains('disconnected')) {
    setPrivateChatEnabled(false);
  } else {
    setPrivateChatEnabled(true);
  }
}

// Handle incoming PM message (async version with proper decryption)
socketHandlers.pm_message = async (data) => {
  const { from, ciphertext } = data;

  try {
    const msg = await utils.decrypt(ciphertext);

    if (!pmSessions.has(from)) {
      pmSessions.set(from, []);
      ensurePmFooterTab(from, from, 'accepted');
    }

    pmSessions.get(from).push({ from, text: msg });

    if (currentPmUser === from) {
      messageHandler.addMessage(elements.privateChatBox, from, msg);
    } else {
      // Flash tab to indicate new message
      const tab = document.getElementById(`pm-tab-${from}`);
      if (tab) {
        tab.classList.add('notify');
        // Remove notification after 5 seconds
        setTimeout(() => tab.classList.remove('notify'), 5000);
      }
    }
  } catch (error) {
    console.error('Error handling PM message:', error);
    if (currentPmUser === from) {
      messageHandler.addMessage(
        elements.privateChatBox,
        from,
        '[Encrypted message - decryption failed]'
      );
    }
  }
};

// Activate tab function
function activateTab(user) {
  document.querySelectorAll('.pm-tab').forEach((btn) => btn.classList.remove('active'));
  document.getElementById(`pm-tab-${user}`)?.classList.add('active');
  currentPmUser = user;
}

// Users panel toggle functionality
let isPanelHidden = true;

function toggleUsersPanel() {
  isPanelHidden = !isPanelHidden;

  if (isPanelHidden) {
    elements.usersPanel.classList.add('hidden');
    elements.mainContainer.classList.add('panel-hidden');
    elements.usersToggle.classList.add('panel-hidden');
    elements.usersToggle.textContent = '👥';
    elements.usersToggle.title = 'Show Users Panel';
  } else {
    // Add loading class temporarily to trigger fade-in
    elements.usersPanel.classList.add('panel-loading');
    elements.usersPanel.classList.remove('hidden');
    elements.mainContainer.classList.remove('panel-hidden');
    elements.usersToggle.classList.remove('panel-hidden');
    elements.usersToggle.textContent = '◀';
    elements.usersToggle.title = 'Hide Users Panel';

    // Remove loading class after a brief delay to trigger fade-in
    setTimeout(() => {
      elements.usersPanel.classList.remove('panel-loading');

      // Stagger the fade-in animations for user items
      setTimeout(() => {
        const userItems = document.querySelectorAll('.online-user');
        userItems.forEach((item, index) => {
          item.style.animationDelay = `${0.4 + index * 0.1}s`;
          item.style.animation = 'none';
          // Force reflow
          item.offsetHeight;
          item.style.animation = 'fadeInUser 0.4s ease forwards';
        });
      }, 50);
    }, 50);
  }
}

// Initialize app
window.addEventListener('DOMContentLoaded', () => {
  // Authentication
  token = utils.getTokenFromCookie('access_token');
  if (!token) {
    window.location.href = '/login';
    return;
  }

  const payload = utils.parseJwt(token);
  if (!payload?.sub) {
    console.error('Invalid token');
    window.location.href = '/login';
    return;
  }

  currentUsername = payload.sub;

  // Update header with username
  const userDisplay = document.getElementById('current-user');
  if (userDisplay) {
    userDisplay.textContent = currentUsername;
  }

  // Event listeners
  elements.logoutBtn?.addEventListener('click', () => {
    document.cookie = 'access_token=; Max-Age=0';
    window.location.href = '/login';
  });

  elements.privateSendBtn.addEventListener('click', sendPrivateMessage);
  elements.privateChatClose.addEventListener('click', closePrivateChat);
  elements.privateChatMinimize.addEventListener('click', minimizePrivateChat);
  elements.privateChatDisconnect.addEventListener('click', disconnectPrivateChat);
  elements.privateInput.addEventListener('keypress', handlePrivateInputKeyPress);

  // Users panel toggle
  elements.usersToggle?.addEventListener('click', toggleUsersPanel);

  // Initialize panel as hidden
  elements.usersPanel.classList.add('hidden');
  elements.mainContainer.classList.add('panel-hidden');
  elements.usersToggle.classList.add('panel-hidden');
  elements.usersToggle.textContent = '👥';
  elements.usersToggle.title = 'Show Users Panel';

  // Generate RSA key pair for encryption
  utils
    .generateKeyPair()
    .then(() => {
      console.log('RSA key pair generated successfully - private messages will be encrypted');
    })
    .catch((error) => {
      console.error('Failed to generate RSA key pair:', error);
      console.error('Private messages will not work without HTTPS or localhost');
    });

  // Connect to WebSocket
  elements.connectingOverlay?.classList.remove('hidden');
  setupSocket();

  // Remove loading class to trigger fade-in animations
  setTimeout(() => {
    elements.usersPanel?.classList.remove('panel-loading');
  }, 100);
});

// Chat form submission
elements.form.addEventListener('submit', (e) => {
  e.preventDefault();

  if (!socket || socket.readyState !== WebSocket.OPEN) {
    console.warn('Socket is not connected.');
    return;
  }

  const message = elements.input.value.trim();
  if (message && currentUsername) {
    socket.send(
      JSON.stringify({
        type: 'chat_message',
        data: { message },
      })
    );
    elements.input.value = '';
  }
});
