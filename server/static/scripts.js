// WebSocket Configuration
const WS_CONFIG = {
  LOCAL_WS_URL: `ws://${window.location.hostname}:8080/ws`,
  PRODUCTION_WS_URL: 'wss://chat.socksthoughtshop.lol/ws',
  // ACTIVE_WS_URL: `ws://${window.location.hostname}:8080/ws`,
  ACTIVE_WS_URL: `wss://chat.socksthoughtshop.lol/ws`,
};

// State management
let socket = null;
let currentUsername = '';
let token = null;
let keyPair = null;
let userPublicKeys = new Map();
let currentPmUser = null;
let isPanelHidden = true;
let isAudioEnabled = true; // Audio toggle state
let audioVolume = 0.5; // Volume level (0.0 to 1.0)
let audioPlaybackRate = 1.3; // Playback speed (0.5x to 2.0x)
let currentAudio = null; // Currently playing audio element
let userHasInteracted = false; // Track if user has interacted (required for iOS audio)
let pendingAudio = null; // Audio waiting to be played after user interaction

// Background settings
let backgroundSettings = {
  brightness: 1.0,
  decaySpeed: 1.5,
  driftIntensity: 1.0,
  glowIntensity: 1.0,
  trailDuration: 1500,
  cursorRadius: 100,
  dotSize: 1.0,
};

// DOM elements cache
const elements = {
  messages: document.getElementById('messages'),
  form: document.getElementById('chat-form'),
  input: document.getElementById('message-input'),
  botToggle: document.getElementById('bot-toggle'),
  onlineUsers: document.getElementById('online-users'),
  connectingOverlay: document.getElementById('connecting-overlay'),
  logoutBtn: document.getElementById('logout-btn'),
  privateChatContainer: document.getElementById('private-chat-container'),
  privateChatBox: document.getElementById('private-chat-box'),
  privateChatClose: document.getElementById('close-private-chat'),
  privateChatMinimize: document.getElementById('minimize-private-chat'),
  privateChatMaximize: document.getElementById('maximize-private-chat'),
  privateInput: document.getElementById('private-input'),
  privateSendBtn: document.getElementById('private-send-btn'),
  usersToggle: document.getElementById('users-toggle'),
  usersPanel: document.getElementById('users-panel'),
  mainContainer: document.querySelector('.main-container'),
  welcomeModal: document.getElementById('welcome-modal'),
  welcomeCloseBtn: document.getElementById('welcome-close'),
  welcomeGotItBtn: document.getElementById('welcome-got-it'),
  helpButton: document.getElementById('help-button'),
  helpModal: document.getElementById('help-modal'),
  helpCloseBtn: document.getElementById('help-close'),
  helpGotItBtn: document.getElementById('help-got-it'),
  audioToggle: document.getElementById('audio-toggle'),
  volumeSlider: document.getElementById('volume-slider'),
  speedToggle: document.getElementById('speed-toggle'),
  speedDisplay: document.querySelector('.speed-display'),
  settingsBtn: document.getElementById('settings-btn'),
  settingsPopup: document.getElementById('settings-popup'),
  brightnessSlider: document.getElementById('brightness-slider'),
  brightnessValue: document.getElementById('brightness-value'),
  decaySlider: document.getElementById('decay-slider'),
  decayValue: document.getElementById('decay-value'),
  driftSlider: document.getElementById('drift-slider'),
  driftValue: document.getElementById('drift-value'),
  glowSlider: document.getElementById('glow-slider'),
  glowValue: document.getElementById('glow-value'),
  trailSlider: document.getElementById('trail-slider'),
  trailValue: document.getElementById('trail-value'),
  radiusSlider: document.getElementById('radius-slider'),
  radiusValue: document.getElementById('radius-value'),
  dotSizeSlider: document.getElementById('dot-size-slider'),
  dotSizeValue: document.getElementById('dot-size-value'),
  resetSettings: document.getElementById('reset-settings'),
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

  scrollToBottom: (element) => {
    element.scrollTop = element.scrollHeight;
  },

  isCryptoAvailable: () => {
    return window.crypto?.subtle?.generateKey;
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
    return keyPair;
  },

  exportPublicKey: async (publicKey) => {
    const exported = await window.crypto.subtle.exportKey('spki', publicKey);
    return btoa(String.fromCharCode(...new Uint8Array(exported)));
  },

  importPublicKey: async (publicKeyString) => {
    const publicKeyBuffer = Uint8Array.from(atob(publicKeyString), (c) => c.charCodeAt(0));
    return window.crypto.subtle.importKey(
      'spki',
      publicKeyBuffer,
      { name: 'RSA-OAEP', hash: 'SHA-256' },
      true,
      ['encrypt']
    );
  },

  encrypt: async (message, recipientUsername) => {
    if (!keyPair || !userPublicKeys.has(recipientUsername)) {
      throw new Error('Encryption not available');
    }

    const publicKey = userPublicKeys.get(recipientUsername);
    const encodedMessage = new TextEncoder().encode(message);
    const encrypted = await window.crypto.subtle.encrypt(
      { name: 'RSA-OAEP' },
      publicKey,
      encodedMessage
    );
    return btoa(String.fromCharCode(...new Uint8Array(encrypted)));
  },

  decrypt: async (ciphertext) => {
    if (!keyPair) throw new Error('No key pair available');

    const encryptedBuffer = Uint8Array.from(atob(ciphertext), (c) => c.charCodeAt(0));
    const decrypted = await window.crypto.subtle.decrypt(
      { name: 'RSA-OAEP' },
      keyPair.privateKey,
      encryptedBuffer
    );
    return new TextDecoder().decode(decrypted);
  },

  linkifyUrls: (text) => {
    return text.replace(
      /(https?:\/\/[^\s]+)/g,
      '<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>'
    );
  },
};

// Message handling
const messageHandler = {
  addMessage: (container, user, message, className = '') => {
    // Handle gallery commands
    const galleryMatch = message.match(/\[GALLERY_SHOW\|(.*?)\|([^|]+)\]/);
    if (galleryMatch) {
      const [fullMatch, imagesStr, title] = galleryMatch;
      const images = imagesStr.includes('||')
        ? imagesStr.split('||').map((img) => img.trim())
        : [imagesStr.trim()];
      ImageGalleryController.showGallery(images, title);
      message =
        message.replace(fullMatch, '').trim() ||
        `📸 Showing ${images.length} image${images.length > 1 ? 's' : ''} for ${title}`;
    }

    // Handle button commands
    message = message.replace(
      /\[BUTTON\|([^|]+)\|([^|]+)\]/g,
      '<button class="chat-button" onclick="sendButtonClick(\'$1\', \'$2\')">$2</button>'
    );

    // Linkify URLs
    message = utils.linkifyUrls(message);

    const msgDiv = document.createElement('div');
    msgDiv.className = `message ${className}`;
    msgDiv.innerHTML = `<span class="user-name">${user}</span><span class="message-text">${message}</span>`;
    container.appendChild(msgDiv);
    utils.scrollToBottom(container);
  },

  showTypingIndicator: (container, botName = 'ChatBot') => {
    messageHandler.hideTypingIndicator(container);
    const typingDiv = document.createElement('div');
    typingDiv.id = 'bot-typing-indicator';
    typingDiv.className = 'typing-indicator';
    typingDiv.innerHTML = `
      <div class="typing-dots">
        <div class="typing-dot"></div>
        <div class="typing-dot"></div>
        <div class="typing-dot"></div>
      </div>
      <span class="typing-text">${botName} is thinking...</span>
    `;
    container.appendChild(typingDiv);
    utils.scrollToBottom(container);
  },

  hideTypingIndicator: (container) => {
    const typingIndicator = container.querySelector('#bot-typing-indicator');
    if (typingIndicator) typingIndicator.remove();
  },

  addPrivateMessage: (container, user, message) => {
    const messageClass = user === currentUsername ? 'sent' : 'received';
    const linkedMessage = utils.linkifyUrls(message);
    const msgDiv = document.createElement('div');
    msgDiv.className = `message ${messageClass}`;
    msgDiv.innerHTML = `<span class="user-name">${user}</span><span class="message-text">${linkedMessage}</span>`;
    container.appendChild(msgDiv);
    utils.scrollToBottom(container);
  },

  addSystemMessage: (container, message) => {
    const linkedMessage = utils.linkifyUrls(message);
    const msgDiv = document.createElement('div');
    msgDiv.className = 'message system';
    msgDiv.innerHTML = linkedMessage;
    container.appendChild(msgDiv);
    utils.scrollToBottom(container);
  },

  handleStreamingChunk: (container, user, chunk, isFirst) => {
    let streamingMessage = container.querySelector('#streaming-message');

    if (isFirst || !streamingMessage) {
      streamingMessage = document.createElement('div');
      streamingMessage.className = 'message bot streaming';
      streamingMessage.id = 'streaming-message';
      streamingMessage.innerHTML = `
        <span class="user-name">${user}</span>
        <span class="message-text"></span>
        <span class="cursor-blink">|</span>
      `;
      container.appendChild(streamingMessage);
    }

    const messageText = streamingMessage.querySelector('.message-text');
    if (messageText && chunk) {
      messageText.textContent += chunk;
    }
    utils.scrollToBottom(container);
  },

  completeStreamingMessage: (container, user) => {
    const streamingMessage = container.querySelector('#streaming-message');
    if (streamingMessage) {
      const messageText = streamingMessage.querySelector('.message-text');
      if (messageText) {
        let content = messageText.textContent;

        // Handle gallery commands
        const galleryMatch = content.match(/\[GALLERY_SHOW\|(.*?)\|([^|]+)\]/);
        if (galleryMatch) {
          const [fullMatch, imagesStr, title] = galleryMatch;
          const images = imagesStr.includes('||')
            ? imagesStr.split('||').map((img) => img.trim())
            : [imagesStr.trim()];
          ImageGalleryController.showGallery(images, title);
          content =
            content.replace(fullMatch, '').trim() ||
            `📸 Showing ${images.length} image${images.length > 1 ? 's' : ''} for ${title}`;
        }

        // Handle button commands
        content = content.replace(
          /\[BUTTON\|([^|]+)\|([^|]+)\]/g,
          '<button class="chat-button" onclick="sendButtonClick(\'$1\', \'$2\')">$2</button>'
        );

        // Linkify URLs
        content = utils.linkifyUrls(content);
        messageText.innerHTML = content;
      }

      const cursor = streamingMessage.querySelector('.cursor-blink');
      if (cursor) cursor.remove();

      // Remove status indicator
      const statusIndicator = streamingMessage.querySelector('.streaming-status');
      if (statusIndicator) statusIndicator.remove();

      streamingMessage.classList.remove('streaming');
      streamingMessage.removeAttribute('id');
    }
  },

  updateStreamingStatus: (container, statusMessage) => {
    const streamingMessage = container.querySelector('#streaming-message');
    if (!streamingMessage) {
      return;
    }

    let statusIndicator = streamingMessage.querySelector('.streaming-status');
    if (!statusIndicator) {
      statusIndicator = document.createElement('div');
      statusIndicator.className = 'streaming-status';
      statusIndicator.innerHTML = `
        <div class="status-text"></div>
      `;
      streamingMessage.appendChild(statusIndicator);
    }

    const statusText = statusIndicator.querySelector('.status-text');
    if (statusText) {
      statusText.textContent = statusMessage;
    }
  },
};

// WebSocket message handlers
const socketHandlers = {
  chat_message: (data) => {
    if (elements.messages) {
      messageHandler.hideTypingIndicator(elements.messages);
      const messageClass =
        data.user === 'ChatBot' ? 'bot' : data.user === 'System' ? 'system' : 'user';
      messageHandler.addMessage(elements.messages, data.user, data.message, messageClass);
    }
  },

  bot_typing: (data) => {
    if (elements.messages && data.typing) {
      messageHandler.showTypingIndicator(elements.messages, data.user);
    }
  },

  bot_message_stream: (data) => {
    if (!elements.messages) return;

    if (data.is_first) {
      messageHandler.hideTypingIndicator(elements.messages);
    }

    if (!data.is_complete) {
      messageHandler.handleStreamingChunk(elements.messages, data.user, data.chunk, data.is_first);

      // Update status indicator if available
      if (data.status !== undefined) {
        messageHandler.updateStreamingStatus(elements.messages, data.status);
      }
    } else {
      messageHandler.completeStreamingMessage(elements.messages, data.user);

      // ✅ Play TTS audio if provided and audio is enabled
      if (data.voice_b64 && isAudioEnabled) {
        // Stop any currently playing audio
        if (currentAudio) {
          currentAudio.pause();
          currentAudio.currentTime = 0;
        }

        // Detect iOS Safari
        const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream;
        const isSafari = /^((?!chrome|android).)*safari/i.test(navigator.userAgent);
        const isIOSSafari = isIOS && isSafari;

        // Debug logging
        console.log('🔍 Device Detection:', {
          userAgent: navigator.userAgent,
          isIOS: isIOS,
          isSafari: isSafari,
          isIOSSafari: isIOSSafari,
        });

        let audio;

        if (isIOSSafari) {
          // iOS Safari: Use Blob URL approach
          try {
            const binary = atob(data.voice_b64);
            const array = new Uint8Array(binary.length);
            for (let i = 0; i < binary.length; i++) {
              array[i] = binary.charCodeAt(i);
            }
            const blob = new Blob([array], { type: 'audio/wav' });
            const blobUrl = URL.createObjectURL(blob);

            audio = new Audio(blobUrl);

            // Clean up blob URL when audio ends or errors
            audio.addEventListener('ended', () => {
              URL.revokeObjectURL(blobUrl);
              currentAudio = null;
            });

            audio.addEventListener('error', () => {
              URL.revokeObjectURL(blobUrl);
              currentAudio = null;
            });

            console.log('🔧 Using Blob URL for iOS Safari');
          } catch (blobErr) {
            console.error('🔧 Blob creation failed, falling back to Data URI:', blobErr);
            audio = new Audio('data:audio/wav;base64,' + data.voice_b64);
          }
        } else {
          // Non-iOS: Use Data URI approach
          audio = new Audio('data:audio/wav;base64,' + data.voice_b64);
        }

        // Set audio properties
        audio.volume = audioVolume;
        audio.playbackRate = audioPlaybackRate;
        audio.preload = 'auto';
        currentAudio = audio;

        // iOS-compatible play with multiple fallbacks
        const playAudio = async () => {
          try {
            // Try to play immediately
            await audio.play();
          } catch (err) {
            console.error('🔇 Initial play failed, trying iOS workaround:', err);

            // iOS Safari workaround: Load and play on user interaction
            audio.load();

            // Try again after a short delay
            setTimeout(async () => {
              try {
                await audio.play();
              } catch (retryErr) {
                console.error('🔇 Audio play failed after retry:', retryErr);
                currentAudio = null;

                // Add play button for iOS users when auto-play fails
                if (isIOSSafari) {
                  addPlayAudioButton(audio, data.voice_b64);
                } else {
                  // Show user-friendly message for other browsers
                  if (retryErr.name === 'NotAllowedError') {
                    messageHandler.addSystemMessage(
                      elements.messages,
                      '🔇 Audio blocked by browser. Try tapping the audio button or interacting with the page first.'
                    );
                  }
                }
              }
            }, 100);
          }
        };

        // Add event listeners
        audio.addEventListener('canplaythrough', () => {
          // Audio is ready to play
        });

        audio.addEventListener('ended', () => {
          currentAudio = null;
        });

        audio.addEventListener('error', (err) => {
          console.error('🔇 Audio error:', err);
          currentAudio = null;
        });

        // Start playing
        playAudio();
      }
    }
  },

  user_list: (data) => {
    if (!elements.onlineUsers) return;
    elements.onlineUsers.innerHTML = '';

    data.users
      .filter((user) => user !== currentUsername)
      .forEach((user, index) => {
        const li = document.createElement('li');
        li.className = 'online-user';

        // Check if PM tab already exists for this user
        const existingTab = document.getElementById(`pm-tab-${user}`);
        const hasPmChat = existingTab !== null;

        const isEncryptionAvailable = utils.isCryptoAvailable();
        const pmDisabled = hasPmChat || !isEncryptionAvailable;
        const pmTitle = hasPmChat
          ? 'PM chat already open'
          : !isEncryptionAvailable
          ? 'Private messages require HTTPS or localhost'
          : 'Send PM invite';

        li.innerHTML = `
        <span class="user-name">${user}</span>
        <button class="pm-button ${pmDisabled ? 'disabled' : ''}" 
                onclick="${pmDisabled ? 'return false;' : `sendPmInvite('${user}')`}" 
                ${pmDisabled ? 'disabled' : ''}
                title="${pmTitle}">
          ${hasPmChat ? '✓' : !isEncryptionAvailable ? '🔒' : 'PM'}
        </button>
      `;
        if (!isPanelHidden) {
          li.style.animationDelay = `${0.4 + index * 0.1}s`;
        }
        elements.onlineUsers.appendChild(li);
      });
  },

  pm_message: async (data) => {
    try {
      const decryptedMessage = await utils.decrypt(data.ciphertext);
      messageHandler.addPrivateMessage(elements.privateChatBox, data.from, decryptedMessage);
      openPrivateChat(data.from);
    } catch (error) {
      console.error('Error handling PM message:', error);
      messageHandler.addPrivateMessage(
        elements.privateChatBox,
        data.from,
        '[Encrypted message - decryption failed]'
      );
    }
  },

  pubkey_request: (data) => {
    sendPublicKey(data.from);
  },

  pubkey_response: async (data) => {
    try {
      const publicKey = await utils.importPublicKey(data.public_key);
      userPublicKeys.set(data.from, publicKey);
    } catch (error) {
      console.error(`Error storing public key for ${data.from}:`, error);
    }
  },

  pm_invite: (data) => {
    showPmInviteToast(data.from);
  },

  pm_accept: (data) => {
    ensurePmFooterTab(data.from, data.from, 'accepted');
    messageHandler.addSystemMessage(
      elements.privateChatBox,
      `${data.from} accepted the private chat.`
    );
    openPrivateChat(data.from);
  },

  pm_decline: (data) => {
    ensurePmFooterTab(data.from, data.from, 'declined');
    messageHandler.addSystemMessage(
      elements.messages,
      'System',
      `${data.from} declined your private chat request.`
    );
  },

  pm_disconnect: (data) => {
    // Remove the PM tab completely when user disconnects
    const tab = document.getElementById(`pm-tab-${data.from}`);
    if (tab) tab.remove();

    // Clear the session
    pmSessions.delete(data.from);

    if (currentPmUser === data.from) {
      messageHandler.addSystemMessage(
        elements.privateChatBox,
        `${data.from} has disconnected from the private chat.`
      );
      setPrivateChatEnabled(false);
      if (elements.privateChatMinimize) {
        elements.privateChatMinimize.style.display = 'none';
      }
      // Clear the current PM user since they disconnected
      currentPmUser = null;
    }
    // Remove the system message from main chat - PM disconnects should be handled in PM context only
  },

  gallery_commands: (data) => {
    if (data.commands) {
      const galleryMatches = [...data.commands.matchAll(/\[GALLERY_SHOW\|(.*?)\|([^|]+)\]/g)];
      galleryMatches.forEach((match) => {
        const [fullMatch, imagesStr, title] = match;
        const images = imagesStr.includes('||')
          ? imagesStr.split('||').map((img) => img.trim())
          : [imagesStr.trim()];
        ImageGalleryController.showGallery(images, title);
      });
    }
  },
};

// Function to add play audio button for iOS users
function addPlayAudioButton(audio, voiceB64) {
  // Find the last bot message
  const messages = document.querySelectorAll('.message.bot');
  if (messages.length === 0) return;

  const lastBotMessage = messages[messages.length - 1];

  // Check if play button already exists
  if (lastBotMessage.querySelector('.ios-play-audio-btn')) return;

  // Create play button
  const playButton = document.createElement('button');
  playButton.className = 'ios-play-audio-btn';
  playButton.innerHTML = '🔊 Play Audio';
  playButton.title = 'Tap to play audio (iOS Safari)';

  // Style the button
  playButton.style.cssText = `
    margin-top: 8px;
    padding: 6px 12px;
    background: linear-gradient(135deg, #667eea, #764ba2);
    border: 1px solid rgba(255, 255, 255, 0.2);
    border-radius: 6px;
    color: white;
    font-size: 12px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
    display: inline-flex;
    align-items: center;
    gap: 4px;
  `;

  // Add hover effects
  playButton.addEventListener('mouseenter', () => {
    playButton.style.transform = 'translateY(-1px)';
    playButton.style.boxShadow = '0 4px 12px rgba(102, 126, 234, 0.3)';
  });

  playButton.addEventListener('mouseleave', () => {
    playButton.style.transform = 'translateY(0)';
    playButton.style.boxShadow = 'none';
  });

  // Add click handler
  playButton.addEventListener('click', async () => {
    try {
      // Mark user interaction
      if (!userHasInteracted) {
        userHasInteracted = true;
      }

      // Try to play the audio
      await audio.play();

      // Remove the button after successful play
      playButton.remove();

      console.log('🔊 iOS audio played successfully via button');
    } catch (err) {
      console.error('🔇 iOS audio play failed via button:', err);

      // Update button text to show error
      playButton.innerHTML = '❌ Play Failed';
      playButton.style.background = 'linear-gradient(135deg, #e74c3c, #c0392b)';
      playButton.disabled = true;

      // Reset after 3 seconds
      setTimeout(() => {
        playButton.innerHTML = '🔊 Play Audio';
        playButton.style.background = 'linear-gradient(135deg, #667eea, #764ba2)';
        playButton.disabled = false;
      }, 3000);
    }
  });

  // Add the button to the message
  lastBotMessage.appendChild(playButton);

  console.log('🔊 Added iOS play audio button');
}

// WebSocket setup
function setupSocket() {
  socket = new WebSocket(`${WS_CONFIG.ACTIVE_WS_URL}?token=${token}`);

  socket.addEventListener('open', () => {
    elements.form.style.pointerEvents = 'auto';
    elements.form.style.opacity = '1';
    elements.connectingOverlay?.classList.add('hidden');
    setTimeout(() => showWelcomeModal(), 500);
  });

  socket.addEventListener('message', (event) => {
    try {
      const data = JSON.parse(event.data);
      const handler = socketHandlers[data.event] || socketHandlers[data.type];
      if (handler) {
        handler(data.data || data);
      } else if (typeof data === 'string') {
        messageHandler.addMessage(elements.messages, 'System', data, 'bot');
      }
    } catch (error) {
      console.error('Error parsing WebSocket message:', error);
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

// Private chat functions
function showPmInviteToast(fromUser) {
  const toastContainer = document.getElementById('invite-toast-container');
  const toast = document.createElement('div');
  toast.className = 'invite-toast';
  toast.innerHTML = `
    <div class="invite-content">
      <div class="invite-icon">💬</div>
      <div class="invite-message">
        <div class="invite-title">Private Chat Invitation</div>
        <div class="invite-subtitle"><b>${fromUser}</b> invited you to a private chat</div>
      </div>
    </div>
    <div class="invite-actions">
      <button class="accept-btn" onclick="acceptPmInvite('${fromUser}', this.closest('.invite-toast'))">
        <span>✓</span> Accept
      </button>
      <button class="decline-btn" onclick="declinePmInvite('${fromUser}', this.closest('.invite-toast'))">
        <span>✕</span> Decline
      </button>
    </div>
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
  requestPublicKey(user);
}

function requestPublicKey(username) {
  socket.send(JSON.stringify({ type: 'pubkey_request', to: username }));
}

async function sendPublicKey(username) {
  try {
    const publicKeyString = await utils.exportPublicKey(keyPair.publicKey);
    socket.send(
      JSON.stringify({ type: 'pubkey_response', to: username, public_key: publicKeyString })
    );
  } catch (error) {
    console.error(`Error sending public key to ${username}:`, error);
  }
}

function acceptPmInvite(user, toast) {
  try {
    socket.send(JSON.stringify({ type: 'pm_accept', to: user }));
    ensurePmFooterTab(user, user, 'accepted');
    openPrivateChat(user);

    // Remove the toast notification
    if (toast && toast.remove) {
      toast.remove();
    } else if (toast && toast.parentNode) {
      toast.parentNode.removeChild(toast);
    }

    requestPublicKey(user);
  } catch (error) {
    console.error('Error accepting PM invite:', error);
    // Still try to remove the toast even if there's an error
    if (toast && toast.remove) {
      toast.remove();
    } else if (toast && toast.parentNode) {
      toast.parentNode.removeChild(toast);
    }
  }
}

function openPrivateChat(user) {
  try {
    currentPmUser = user;

    // Check if elements exist before accessing them
    if (elements.privateChatContainer) {
      elements.privateChatContainer.style.display = 'flex';
      elements.privateChatContainer.classList.remove('hidden');
      elements.privateChatContainer.dataset.user = user;
    }

    const chatUserName = document.getElementById('chat-user-name');
    if (chatUserName) chatUserName.textContent = `with ${user}`;

    // Show control buttons
    if (elements.privateChatMinimize) {
      elements.privateChatMinimize.style.display = 'inline-block';
    }
    if (elements.privateChatClose) {
      elements.privateChatClose.style.display = 'inline-block';
    }

    if (elements.privateChatBox) {
      elements.privateChatBox.innerHTML = '';
      const messages = pmSessions.get(user) || [];

      if (messages.length === 0) {
        messageHandler.addSystemMessage(
          elements.privateChatBox,
          `Private chat with <b>${user}</b> started.`
        );
      } else {
        messages.forEach(({ from, text }) => {
          messageHandler.addPrivateMessage(elements.privateChatBox, from, text);
        });
      }
    }

    activateTab(user);
    const tab = document.getElementById(`pm-tab-${user}`);
    if (tab?.classList.contains('disconnected')) {
      setPrivateChatEnabled(false);
      if (elements.privateChatMinimize) {
        elements.privateChatMinimize.style.display = 'none';
      }
    } else {
      setPrivateChatEnabled(true);
    }
  } catch (error) {
    console.error('Error opening private chat:', error);
  }
}

async function sendPrivateMessage() {
  const msg = elements.privateInput.value.trim();
  const to = elements.privateChatContainer.dataset.user;

  if (msg && to) {
    try {
      const ciphertext = await utils.encrypt(msg, to);
      socket.send(JSON.stringify({ type: 'pm_message', to, ciphertext }));
      messageHandler.addPrivateMessage(elements.privateChatBox, currentUsername, msg);
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
  const currentUser = elements.privateChatContainer.dataset.user;
  if (currentUser) {
    // Send disconnect message to the other user
    socket.send(JSON.stringify({ type: 'pm_disconnect', to: currentUser }));

    // Remove the PM tab completely (regardless of status)
    const tab = document.getElementById(`pm-tab-${currentUser}`);
    if (tab) tab.remove();

    // Clear the session
    pmSessions.delete(currentUser);

    // Clear the current PM user
    if (currentPmUser === currentUser) currentPmUser = null;
  }

  // Hide the chat container
  elements.privateChatContainer.classList.add('hidden');
  elements.privateChatBox.innerHTML = '';
  delete elements.privateChatContainer.dataset.user;

  // Clear the chat user name
  const chatUserName = document.getElementById('chat-user-name');
  if (chatUserName) chatUserName.textContent = '';

  // Clear active state from all PM tabs
  document.querySelectorAll('.pm-tab').forEach((tab) => tab.classList.remove('active'));

  // Disable the chat input
  setPrivateChatEnabled(false);

  // Update PM button states in the user list
  updatePmButtonStates();
}

function minimizePrivateChat() {
  elements.privateChatContainer.classList.add('hidden');

  // Clear active state from all PM tabs
  document.querySelectorAll('.pm-tab').forEach((tab) => tab.classList.remove('active'));

  // Clear the current PM user since chat is minimized
  currentPmUser = null;
}

function maximizePrivateChat() {
  const container = elements.privateChatContainer;
  const button = elements.privateChatMaximize;
  const svg = button.querySelector('svg');

  if (container.classList.contains('maximized')) {
    container.classList.remove('maximized');
    button.title = 'Maximize';
    svg.innerHTML =
      '<rect x="3" y="3" width="18" height="18" rx="2" ry="2" /><polyline points="8,8 16,8 16,16" />';
  } else {
    container.classList.add('maximized');
    button.title = 'Restore';
    svg.innerHTML =
      '<rect x="3" y="3" width="18" height="18" rx="2" ry="2" /><rect x="8" y="8" width="10" height="10" rx="1" ry="1" />';
  }
}

function setPrivateChatEnabled(enabled) {
  elements.privateInput.disabled = !enabled;
  elements.privateSendBtn.disabled = !enabled;
  elements.privateInput.placeholder = enabled
    ? 'Type a private message...'
    : 'Private chat disconnected';
}

function handlePrivateInputKeyPress(event) {
  if (event.key === 'Enter') {
    event.preventDefault();
    sendPrivateMessage();
  }
}

// PM Session Management
const pmSessions = new Map();

// Function to update PM button states in the user list
function updatePmButtonStates() {
  const userItems = document.querySelectorAll('.online-user');
  userItems.forEach((userItem) => {
    const userName = userItem.querySelector('.user-name')?.textContent;
    if (!userName) return;

    const pmButton = userItem.querySelector('.pm-button');
    if (!pmButton) return;

    // Check if PM tab already exists for this user
    const existingTab = document.getElementById(`pm-tab-${userName}`);
    const hasPmChat = existingTab !== null;

    // Update button state
    if (hasPmChat) {
      pmButton.classList.add('disabled');
      pmButton.disabled = true;
      pmButton.textContent = '✓';
      pmButton.title = 'PM chat already open';
      pmButton.onclick = () => false;
    } else {
      pmButton.classList.remove('disabled');
      pmButton.disabled = false;
      pmButton.textContent = 'PM';
      pmButton.title = 'Send PM invite';
      pmButton.onclick = () => sendPmInvite(userName);
    }
  });
}

function ensurePmFooterTab(chatId, userName, status) {
  const footer = document.getElementById('pm-footer');
  if (!footer) {
    console.error('PM footer not found!');
    return;
  }

  const tabId = `pm-tab-${chatId}`;
  let tab = document.getElementById(tabId);

  if (!tab && status !== 'declined') {
    tab = document.createElement('div');
    tab.id = tabId;
    tab.className = 'pm-tab';

    // Create status dot
    const statusDot = document.createElement('div');
    statusDot.className = 'status-dot';
    tab.appendChild(statusDot);

    // Create text content without overwriting the status dot
    const textSpan = document.createElement('span');
    if (status === 'pending') {
      tab.classList.add('pending');
      textSpan.textContent = `${userName} (pending)`;
    } else if (status === 'accepted') {
      tab.classList.add('accepted');
      textSpan.textContent = userName;
    } else if (status === 'disconnected') {
      tab.classList.add('disconnected');
      textSpan.textContent = `${userName} (offline)`;
    }
    tab.appendChild(textSpan);

    tab.addEventListener('click', function () {
      if (elements.privateChatContainer.classList.contains('hidden')) {
        elements.privateChatContainer.classList.remove('hidden');
        switchToPmChat(chatId);
      } else {
        elements.privateChatContainer.classList.add('hidden');
      }

      document.querySelectorAll('.pm-tab').forEach((t) => t.classList.remove('active'));
      if (!elements.privateChatContainer.classList.contains('hidden')) {
        tab.classList.add('active');
      }
    });

    footer.appendChild(tab);

    // Update PM button states in the user list
    updatePmButtonStates();
  } else if (tab) {
    if (!tab.classList.contains('disconnected')) {
      tab.classList.remove('pending', 'accepted');
    }

    // Update text content without overwriting the status dot
    let textSpan = tab.querySelector('span');
    if (!textSpan) {
      textSpan = document.createElement('span');
      tab.appendChild(textSpan);
    }

    if (status === 'pending') {
      tab.classList.add('pending');
      textSpan.textContent = `${userName} (pending)`;
    } else if (status === 'accepted') {
      tab.classList.add('accepted');
      textSpan.textContent = userName;
    } else if (status === 'disconnected') {
      tab.classList.add('disconnected');
      textSpan.textContent = `${userName} (offline)`;
    }
  }

  if (status === 'declined' && tab) {
    footer.removeChild(tab);

    // Update PM button states in the user list
    updatePmButtonStates();
  }
}

function switchToPmChat(user) {
  currentPmUser = user;
  elements.privateChatContainer.dataset.user = user;

  const chatUserName = document.getElementById('chat-user-name');
  if (chatUserName) chatUserName.textContent = `with ${user}`;

  document.querySelectorAll('.pm-tab').forEach((btn) => btn.classList.remove('active'));
  document.getElementById(`pm-tab-${user}`)?.classList.add('active');

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
      messageHandler.addPrivateMessage(elements.privateChatBox, from, text);
    });
  }

  // Clear unread status when switching to this chat
  clearUnreadStatus(user);

  if (document.getElementById(`pm-tab-${user}`)?.classList.contains('disconnected')) {
    setPrivateChatEnabled(false);
  } else {
    setPrivateChatEnabled(true);
  }
}

function activateTab(user) {
  document.querySelectorAll('.pm-tab').forEach((btn) => btn.classList.remove('active'));
  document.getElementById(`pm-tab-${user}`)?.classList.add('active');
  currentPmUser = user;
}

// Users panel toggle
function toggleUsersPanel() {
  isPanelHidden = !isPanelHidden;

  if (isPanelHidden) {
    elements.usersPanel.classList.add('hidden');
    elements.mainContainer.classList.add('panel-hidden');
    elements.usersToggle.classList.add('panel-hidden');
    elements.usersToggle.textContent = '👥';
    elements.usersToggle.title = 'Show Users Panel';
  } else {
    elements.usersPanel.classList.add('panel-loading');
    elements.usersPanel.classList.remove('hidden');
    elements.mainContainer.classList.remove('panel-hidden');
    elements.usersToggle.classList.remove('panel-hidden');
    elements.usersToggle.textContent = '◀';
    elements.usersToggle.title = 'Hide Users Panel';

    setTimeout(() => {
      elements.usersPanel.classList.remove('panel-loading');
      setTimeout(() => {
        const userItems = document.querySelectorAll('.online-user');
        userItems.forEach((item, index) => {
          item.style.animationDelay = `${0.4 + index * 0.1}s`;
          item.style.animation = 'none';
          item.offsetHeight;
          item.style.animation = 'fadeInUser 0.4s ease forwards';
        });
      }, 50);
    }, 50);
  }
}

// Modal functions
function showWelcomeModal() {
  elements.welcomeModal?.classList.remove('hidden');
  document.body.classList.add('modal-open');
}

function hideWelcomeModal() {
  elements.welcomeModal?.classList.add('hidden');
  document.body.classList.remove('modal-open');
}

function setupWelcomeModalHandlers() {
  elements.welcomeCloseBtn?.addEventListener('click', hideWelcomeModal);
  elements.welcomeGotItBtn?.addEventListener('click', hideWelcomeModal);
  elements.welcomeModal?.addEventListener('click', (e) => {
    if (e.target === elements.welcomeModal) hideWelcomeModal();
  });

  document.querySelectorAll('.example-tag').forEach((tag) => {
    tag.addEventListener('click', () => {
      elements.input.value = tag.textContent;
      elements.input.focus();
      hideWelcomeModal();
    });
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !elements.welcomeModal?.classList.contains('hidden')) {
      hideWelcomeModal();
    }
  });

  // Welcome modal page navigation
  let currentWelcomePage = 1;
  const welcomePages = ['welcome-page-1', 'welcome-page-2'];
  const welcomeModalTitle = document.getElementById('welcome-modal-title');
  const welcomePrevBtn = document.getElementById('welcome-prev-page');
  const welcomeNextBtn = document.getElementById('welcome-next-page');

  function showWelcomePage(pageNum) {
    // Hide all pages
    welcomePages.forEach((pageId, index) => {
      const page = document.getElementById(pageId);
      if (page) {
        page.classList.toggle('hidden', index + 1 !== pageNum);
      }
    });

    // Update navigation buttons
    if (welcomePrevBtn) {
      welcomePrevBtn.style.display = pageNum === 1 ? 'none' : 'inline-block';
    }
    if (welcomeNextBtn) {
      welcomeNextBtn.style.display = pageNum === welcomePages.length ? 'none' : 'inline-block';
    }

    // Show/hide "Got it!" button based on page
    if (elements.welcomeGotItBtn) {
      elements.welcomeGotItBtn.style.display = pageNum === 2 ? 'inline-block' : 'none';
    }

    // Update title
    if (welcomeModalTitle) {
      welcomeModalTitle.textContent =
        pageNum === 1 ? "🤖 Welcome to Ryan's Portfolio Chat" : '💡 What can I ask the bot?';
    }

    currentWelcomePage = pageNum;
  }

  // Navigation button handlers
  if (welcomePrevBtn) {
    welcomePrevBtn.addEventListener('click', () => {
      if (currentWelcomePage > 1) {
        showWelcomePage(currentWelcomePage - 1);
      }
    });
  }

  if (welcomeNextBtn) {
    welcomeNextBtn.addEventListener('click', () => {
      if (currentWelcomePage < welcomePages.length) {
        showWelcomePage(currentWelcomePage + 1);
      }
    });
  }

  // Reset to page 1 when modal is shown
  const originalShowWelcomeModal = showWelcomeModal;
  showWelcomeModal = () => {
    originalShowWelcomeModal();
    showWelcomePage(1);
  };
}

function showHelpModal() {
  elements.helpModal?.classList.remove('hidden');
  document.body.classList.add('modal-open');
}

function hideHelpModal() {
  elements.helpModal?.classList.add('hidden');
  document.body.classList.remove('modal-open');
}

function setupHelpModalHandlers() {
  elements.helpButton?.addEventListener('click', (e) => {
    e.preventDefault();
    showHelpModal();
  });

  elements.helpCloseBtn?.addEventListener('click', hideHelpModal);
  elements.helpGotItBtn?.addEventListener('click', hideHelpModal);
  elements.helpModal?.addEventListener('click', (e) => {
    if (e.target === elements.helpModal) hideHelpModal();
  });
}

window.insertQuestion = function (element) {
  const question = element.textContent;
  if (elements.input) {
    elements.input.value = question;
    elements.input.focus();
    if (elements.botToggle && !elements.botToggle.classList.contains('active')) {
      elements.botToggle.click();
    }
  }
  hideHelpModal();
};

// Image Gallery Controller
const ImageGalleryController = {
  currentImages: [],
  currentIndex: 0,
  isVisible: false,

  showGallery(images, title = 'Project Images') {
    const container = document.getElementById('image-gallery-container');
    const titleElement = document.getElementById('gallery-title');
    const imagesContainer = document.getElementById('gallery-images');

    if (!container || !imagesContainer) return;

    this.currentImages = images;
    this.currentIndex = 0;
    this.isVisible = true;

    titleElement.textContent = title;
    imagesContainer.innerHTML = '';

    images.forEach((imageSrc, index) => {
      const img = document.createElement('img');
      img.src = `/static/assets/${imageSrc}`;
      img.alt = `${title} - Image ${index + 1}`;
      img.className = index === 0 ? 'active' : '';
      imagesContainer.appendChild(img);
    });

    this.updateCounter();
    this.updateNavButtons();
    container.classList.remove('hidden');
  },

  hideGallery() {
    const container = document.getElementById('image-gallery-container');
    if (container) {
      container.classList.add('hidden');
      this.isVisible = false;
      this.currentImages = [];
      this.currentIndex = 0;
    }
  },

  nextImage() {
    if (this.currentImages.length <= 1) return;

    const images = document.querySelectorAll('#gallery-images img');
    if (images.length === 0) return;

    images[this.currentIndex].classList.remove('active');
    this.currentIndex = (this.currentIndex + 1) % this.currentImages.length;
    images[this.currentIndex].classList.add('active');
    this.updateCounter();
    this.updateNavButtons();
  },

  previousImage() {
    if (this.currentImages.length <= 1) return;

    const images = document.querySelectorAll('#gallery-images img');
    if (images.length === 0) return;

    images[this.currentIndex].classList.remove('active');
    this.currentIndex =
      this.currentIndex === 0 ? this.currentImages.length - 1 : this.currentIndex - 1;
    images[this.currentIndex].classList.add('active');
    this.updateCounter();
    this.updateNavButtons();
  },

  updateCounter() {
    const counter = document.getElementById('gallery-counter');
    if (counter && this.currentImages.length > 0) {
      counter.textContent = `${this.currentIndex + 1} of ${this.currentImages.length}`;
    }
  },

  updateNavButtons() {
    const prevBtn = document.getElementById('gallery-prev');
    const nextBtn = document.getElementById('gallery-next');
    if (prevBtn && nextBtn) {
      const hasMultipleImages = this.currentImages.length > 1;
      prevBtn.disabled = !hasMultipleImages;
      nextBtn.disabled = !hasMultipleImages;
    }
  },
};

// Three.js Background System (Simplified)
const backgroundSystem = {
  scene: null,
  camera: null,
  renderer: null,
  particles: [],
  mouseX: 0,
  mouseY: 0,
  isEnabled: false,

  init() {
    try {
      this.setupThreeJS();
      this.createParticles();
      this.addEventListeners();
      this.isEnabled = true;
      this.startRenderLoop();
    } catch (error) {
      console.error('Error initializing background system:', error);
    }
  },

  setupThreeJS() {
    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(
      40,
      window.innerWidth / window.innerHeight,
      0.1,
      2000
    );
    this.camera.position.set(0, 0, 400);
    this.camera.lookAt(0, 0, 0);
    this.camera.rotation.x = 0.1;

    this.renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
    this.renderer.setSize(window.innerWidth, window.innerHeight);
    this.renderer.domElement.style.position = 'fixed';
    this.renderer.domElement.style.top = '0';
    this.renderer.domElement.style.left = '0';
    this.renderer.domElement.style.zIndex = '-1';
    this.renderer.domElement.style.pointerEvents = 'none';
    document.body.appendChild(this.renderer.domElement);
  },

  createParticles() {
    this.particles = [];
    const gridWidth = 90;
    const gridHeight = 50;
    const spacingX = 15;
    const spacingY = 15;
    const depthRange = 350;
    const baseSize = 1 * backgroundSettings.dotSize;

    const startX = -(gridWidth * spacingX) / 2;
    const startY = -(gridHeight * spacingY) / 2;

    for (let x = 0; x < gridWidth; x++) {
      for (let y = 0; y < gridHeight; y++) {
        const posX = startX + x * spacingX;
        const posY = startY + y * spacingY;
        const depthProgress = (gridHeight - 1 - y) / (gridHeight - 1);
        const posZ = depthRange * (depthProgress - 0.8);

        const material = new THREE.MeshBasicMaterial({
          color: new THREE.Color(1, 1, 1),
          transparent: true,
          opacity: 0.15,
        });

        const geometry = new THREE.CircleGeometry(baseSize, 8);
        const particle = new THREE.Mesh(geometry, material);
        particle.position.set(posX, posY, posZ);

        particle.userData = {
          screenX: 0,
          screenY: 0,
          world3D: { x: posX, y: posY, z: posZ },
          originalOpacity: 0.15,
          originalSize: baseSize,
          targetOpacity: 0.15,
          targetColor: new THREE.Color(1, 1, 1),
        };

        this.scene.add(particle);
        this.particles.push(particle);
      }
    }
  },

  addEventListeners() {
    document.addEventListener('mousemove', (e) => {
      this.mouseX = e.clientX;
      this.mouseY = e.clientY;
    });

    window.addEventListener('resize', () => {
      this.camera.aspect = window.innerWidth / window.innerHeight;
      this.camera.updateProjectionMatrix();
      this.renderer.setSize(window.innerWidth, window.innerHeight);
    });
  },

  updateParticles() {
    if (!this.isEnabled) return;

    const time = Date.now() * 0.001;
    const driftX = Math.sin(time * 0.25) * 8 * backgroundSettings.driftIntensity;
    const driftY = Math.cos(time * 0.25) * 6 * backgroundSettings.driftIntensity;
    const driftZ = Math.sin(time * 0.2) * 3 * backgroundSettings.driftIntensity;

    this.particles.forEach((particle) => {
      const currentX = particle.userData.world3D.x + driftX;
      const currentY = particle.userData.world3D.y + driftY;
      const currentZ = particle.userData.world3D.z + driftZ;

      particle.position.set(currentX, currentY, currentZ);

      const vector = new THREE.Vector3(currentX, currentY, currentZ);
      vector.project(this.camera);

      const screenX = (vector.x * 0.5 + 0.5) * window.innerWidth;
      const screenY = (-vector.y * 0.5 + 0.5) * window.innerHeight;

      particle.userData.screenX = screenX;
      particle.userData.screenY = screenY;

      const distance = Math.sqrt((this.mouseX - screenX) ** 2 + (this.mouseY - screenY) ** 2);
      const cursorRadius = backgroundSettings.cursorRadius;

      if (distance <= cursorRadius) {
        const intensity = 1 - distance / cursorRadius;
        particle.userData.targetOpacity =
          particle.userData.originalOpacity * backgroundSettings.brightness +
          intensity * 1.2 * backgroundSettings.glowIntensity;
        particle.userData.targetColor = new THREE.Color(1, 0.42, 0.42);
        particle.userData.lastGlowTime = Date.now();
      } else {
        const timeSinceGlow = Date.now() - (particle.userData.lastGlowTime || 0);
        const trailDuration = backgroundSettings.trailDuration;

        if (timeSinceGlow < trailDuration) {
          const fadeProgress = timeSinceGlow / trailDuration;
          const trailIntensity = 1 - fadeProgress;
          particle.userData.targetOpacity =
            particle.userData.originalOpacity * backgroundSettings.brightness +
            trailIntensity * 0.8 * backgroundSettings.glowIntensity;
        } else {
          particle.userData.targetOpacity =
            particle.userData.originalOpacity * backgroundSettings.brightness;
          particle.userData.targetColor = new THREE.Color(1, 1, 1);
        }
      }

      const lerpSpeed = 0.02 * backgroundSettings.decaySpeed;
      particle.material.opacity = THREE.MathUtils.lerp(
        particle.material.opacity,
        particle.userData.targetOpacity,
        lerpSpeed
      );
      particle.material.color.lerp(particle.userData.targetColor, lerpSpeed);
    });
  },

  startRenderLoop() {
    const animate = () => {
      if (this.isEnabled) {
        this.updateParticles();
        this.renderer.render(this.scene, this.camera);
        requestAnimationFrame(animate);
      }
    };
    // Only start if not already running
    if (!this.renderLoopStarted) {
      this.renderLoopStarted = true;
      requestAnimationFrame(animate);
    }
  },

  updateParticleSizes() {
    const baseSize = 1 * backgroundSettings.dotSize;
    this.particles.forEach((particle) => {
      // Create new geometry with updated size
      const newGeometry = new THREE.CircleGeometry(baseSize, 8);
      particle.geometry.dispose();
      particle.geometry = newGeometry;
      particle.userData.originalSize = baseSize;
    });
  },
};

// Initialize app
window.addEventListener('DOMContentLoaded', () => {
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

  const userDisplay = document.getElementById('current-user');
  if (userDisplay) userDisplay.textContent = currentUsername;

  // Track user interactions for iOS audio compatibility
  const markUserInteraction = () => {
    if (!userHasInteracted) {
      userHasInteracted = true;
      console.log('✅ User interaction detected - audio can now play');

      // Try to play any pending audio
      if (pendingAudio) {
        pendingAudio.play().catch((err) => {
          console.log("🔇 Still can't play pending audio:", err);
        });
        pendingAudio = null;
      } else if (currentAudio && currentAudio.paused) {
        currentAudio.play().catch((err) => {
          console.log("🔇 Still can't play audio:", err);
        });
      }
    }
  };

  // Listen for various user interactions
  document.addEventListener('click', markUserInteraction, { once: true });
  document.addEventListener('touchstart', markUserInteraction, { once: true });
  document.addEventListener('keydown', markUserInteraction, { once: true });
  document.addEventListener('scroll', markUserInteraction, { once: true });

  // Event listeners
  elements.logoutBtn?.addEventListener('click', () => {
    document.cookie = 'access_token=; Max-Age=0';
    window.location.href = '/login';
  });

  elements.privateSendBtn.addEventListener('click', sendPrivateMessage);
  elements.privateChatClose.addEventListener('click', closePrivateChat);
  elements.privateChatMinimize.addEventListener('click', minimizePrivateChat);
  elements.privateChatMaximize.addEventListener('click', maximizePrivateChat);
  elements.privateInput.addEventListener('keypress', handlePrivateInputKeyPress);
  elements.usersToggle?.addEventListener('click', toggleUsersPanel);

  setupWelcomeModalHandlers();
  setupHelpModalHandlers();

  elements.usersPanel.classList.add('hidden');
  elements.mainContainer.classList.add('panel-hidden');
  elements.usersToggle.classList.add('panel-hidden');
  elements.usersToggle.textContent = '👥';
  elements.usersToggle.title = 'Show Users Panel';

  // Only generate RSA key pair if Web Crypto API is available (HTTPS or localhost)
  if (utils.isCryptoAvailable()) {
    utils.generateKeyPair().catch((error) => {
      console.error('Failed to generate RSA key pair:', error);
    });
  } else {
    console.log(
      '🔐 Skipping RSA key generation - Web Crypto API not available (requires HTTPS or localhost)'
    );
    console.log('🔐 Private messages will not be available');
  }

  elements.connectingOverlay?.classList.remove('hidden');
  setupSocket();

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

  let message = elements.input.value.trim();
  if (message && currentUsername) {
    if (
      elements.botToggle.classList.contains('active') &&
      !message.toLowerCase().startsWith('@bot')
    ) {
      message = '@bot ' + message;
    }

    socket.send(
      JSON.stringify({
        type: 'chat_message',
        data: { message },
      })
    );
    elements.input.value = '';
  }
});

// Bot toggle functionality
if (elements.botToggle && elements.input) {
  let isActive = true;

  const updateBotState = () => {
    if (isActive) {
      elements.input.placeholder = 'Ask the bot anything...';
      elements.botToggle.classList.add('active');
    } else {
      elements.input.placeholder = 'Type a message...';
      elements.botToggle.classList.remove('active');
    }
  };

  updateBotState();

  elements.botToggle.addEventListener('click', (e) => {
    e.preventDefault();
    isActive = !isActive;
    updateBotState();
  });
}

// Audio toggle functionality
if (elements.audioToggle) {
  const updateAudioState = () => {
    if (isAudioEnabled) {
      elements.audioToggle.classList.add('active');
      elements.audioToggle.querySelector('span').textContent = '🔊';
      elements.audioToggle.title = 'Audio Enabled (Click to disable)';
    } else {
      elements.audioToggle.classList.remove('active');
      elements.audioToggle.querySelector('span').textContent = '🔇';
      elements.audioToggle.title = 'Audio Disabled (Click to enable)';
    }
  };

  updateAudioState();

  elements.audioToggle.addEventListener('click', (e) => {
    e.preventDefault();
    isAudioEnabled = !isAudioEnabled;

    // Mark user interaction for iOS audio
    userHasInteracted = true;

    // If audio is being disabled, stop any currently playing audio
    if (!isAudioEnabled && currentAudio) {
      currentAudio.pause();
      currentAudio.currentTime = 0;
      currentAudio = null;
    }

    updateAudioState();
  });
} else {
  console.error('🔊 Audio toggle element not found!');
}

// Volume slider functionality
if (elements.volumeSlider) {
  // Set initial volume
  elements.volumeSlider.value = audioVolume * 100;

  elements.volumeSlider.addEventListener('input', (e) => {
    audioVolume = e.target.value / 100;

    // Apply volume change to currently playing audio
    if (currentAudio) {
      currentAudio.volume = audioVolume;
    }
  });

  // Prevent volume slider from triggering audio toggle
  elements.volumeSlider.addEventListener('click', (e) => {
    e.stopPropagation();
  });

  // Touch event handlers for better mobile control
  elements.volumeSlider.addEventListener('touchstart', (e) => {
    e.stopPropagation();
  });

  elements.volumeSlider.addEventListener('touchmove', (e) => {
    e.stopPropagation();
  });

  elements.volumeSlider.addEventListener('touchend', (e) => {
    e.stopPropagation();
  });
} else {
  console.error('🔊 Volume slider element not found!');
}

// Speed control functionality
if (elements.speedToggle) {
  // Set initial speed display
  if (elements.speedDisplay) {
    elements.speedDisplay.textContent = audioPlaybackRate.toFixed(1) + 'x';
  }

  // Mouse wheel event handler
  elements.speedToggle.addEventListener('wheel', (e) => {
    e.preventDefault();

    // Determine scroll direction and adjust speed
    const delta = e.deltaY > 0 ? -0.1 : 0.1;
    const newSpeed = Math.max(0.5, Math.min(2.0, audioPlaybackRate + delta));

    // Only update if speed actually changed
    if (newSpeed !== audioPlaybackRate) {
      audioPlaybackRate = newSpeed;

      // Update speed display
      if (elements.speedDisplay) {
        elements.speedDisplay.textContent = audioPlaybackRate.toFixed(1) + 'x';
      }

      // Apply speed change to currently playing audio
      if (currentAudio) {
        currentAudio.playbackRate = audioPlaybackRate;
      }
    }
  });

  // Prevent default click behavior
  elements.speedToggle.addEventListener('click', (e) => {
    e.preventDefault();
  });

  // Touch event handlers for speed control
  let touchStartY = 0;
  let touchStartTime = 0;

  elements.speedToggle.addEventListener('touchstart', (e) => {
    e.preventDefault();
    touchStartY = e.touches[0].clientY;
    touchStartTime = Date.now();

    // Add visual feedback for touch
    elements.speedToggle.classList.add('touch-active');
  });

  elements.speedToggle.addEventListener('touchmove', (e) => {
    e.preventDefault();
    const touchY = e.touches[0].clientY;
    const deltaY = touchStartY - touchY;

    // Only adjust speed if there's significant movement
    if (Math.abs(deltaY) > 10) {
      const delta = deltaY > 0 ? 0.1 : -0.1;
      const newSpeed = Math.max(0.5, Math.min(2.0, audioPlaybackRate + delta));

      if (newSpeed !== audioPlaybackRate) {
        audioPlaybackRate = newSpeed;

        // Update speed display
        if (elements.speedDisplay) {
          elements.speedDisplay.textContent = audioPlaybackRate.toFixed(1) + 'x';
        }

        // Apply speed change to currently playing audio
        if (currentAudio) {
          currentAudio.playbackRate = audioPlaybackRate;
        }
      }

      touchStartY = touchY;
    }
  });

  elements.speedToggle.addEventListener('touchend', (e) => {
    e.preventDefault();

    // Remove visual feedback when touch ends
    elements.speedToggle.classList.remove('touch-active');
  });

  elements.speedToggle.addEventListener('touchcancel', (e) => {
    e.preventDefault();

    // Remove visual feedback if touch is cancelled
    elements.speedToggle.classList.remove('touch-active');
  });
} else {
  console.error('⚡ Speed control element not found!');
}

// Settings functionality
if (elements.settingsBtn) {
  // Toggle settings popup
  elements.settingsBtn.addEventListener('click', (e) => {
    e.preventDefault();
    elements.settingsPopup.classList.toggle('hidden');
  });

  // Close settings when clicking outside
  document.addEventListener('click', (e) => {
    if (!elements.settingsPopup.contains(e.target) && !elements.settingsBtn.contains(e.target)) {
      elements.settingsPopup.classList.add('hidden');
    }
  });

  // Initialize sliders with current values
  if (elements.brightnessSlider) {
    elements.brightnessSlider.value = backgroundSettings.brightness * 100;
    elements.brightnessValue.textContent = Math.round(backgroundSettings.brightness * 100) + '%';

    elements.brightnessSlider.addEventListener('input', (e) => {
      backgroundSettings.brightness = e.target.value / 100;
      elements.brightnessValue.textContent = e.target.value + '%';
      updateBackgroundSettings();
    });
  }

  if (elements.decaySlider) {
    elements.decaySlider.value = backgroundSettings.decaySpeed * 100;
    elements.decayValue.textContent = Math.round(backgroundSettings.decaySpeed * 100) + '%';

    elements.decaySlider.addEventListener('input', (e) => {
      backgroundSettings.decaySpeed = e.target.value / 100;
      elements.decayValue.textContent = e.target.value + '%';
      updateBackgroundSettings();
    });
  }

  if (elements.driftSlider) {
    elements.driftSlider.value = backgroundSettings.driftIntensity * 100;
    elements.driftValue.textContent = Math.round(backgroundSettings.driftIntensity * 100) + '%';

    elements.driftSlider.addEventListener('input', (e) => {
      backgroundSettings.driftIntensity = e.target.value / 100;
      elements.driftValue.textContent = e.target.value + '%';
      updateBackgroundSettings();
    });
  }

  if (elements.glowSlider) {
    elements.glowSlider.value = backgroundSettings.glowIntensity * 100;
    elements.glowValue.textContent = Math.round(backgroundSettings.glowIntensity * 100) + '%';

    elements.glowSlider.addEventListener('input', (e) => {
      backgroundSettings.glowIntensity = e.target.value / 100;
      elements.glowValue.textContent = e.target.value + '%';
      updateBackgroundSettings();
    });
  }

  if (elements.trailSlider) {
    elements.trailSlider.value = backgroundSettings.trailDuration;
    elements.trailValue.textContent = (backgroundSettings.trailDuration / 1000).toFixed(1) + 's';

    elements.trailSlider.addEventListener('input', (e) => {
      backgroundSettings.trailDuration = parseInt(e.target.value);
      elements.trailValue.textContent = (backgroundSettings.trailDuration / 1000).toFixed(1) + 's';
      updateBackgroundSettings();
    });
  }

  if (elements.radiusSlider) {
    elements.radiusSlider.value = backgroundSettings.cursorRadius;
    elements.radiusValue.textContent = backgroundSettings.cursorRadius + 'px';

    elements.radiusSlider.addEventListener('input', (e) => {
      backgroundSettings.cursorRadius = parseInt(e.target.value);
      elements.radiusValue.textContent = backgroundSettings.cursorRadius + 'px';
      updateBackgroundSettings();
    });
  }

  if (elements.dotSizeSlider) {
    elements.dotSizeSlider.value = backgroundSettings.dotSize * 100;
    elements.dotSizeValue.textContent = Math.round(backgroundSettings.dotSize * 100) + '%';

    elements.dotSizeSlider.addEventListener('input', (e) => {
      backgroundSettings.dotSize = e.target.value / 100;
      elements.dotSizeValue.textContent = e.target.value + '%';
      updateBackgroundSettings();
    });
  }

  // Reset settings
  if (elements.resetSettings) {
    elements.resetSettings.addEventListener('click', () => {
      backgroundSettings = {
        brightness: 1.0,
        decaySpeed: 1.5,
        driftIntensity: 1.0,
        glowIntensity: 1.0,
        trailDuration: 1500,
        cursorRadius: 100,
        dotSize: 1.0,
      };

      // Update sliders
      if (elements.brightnessSlider) {
        elements.brightnessSlider.value = 100;
        elements.brightnessValue.textContent = '100%';
      }
      if (elements.decaySlider) {
        elements.decaySlider.value = 150;
        elements.decayValue.textContent = '150%';
      }
      if (elements.driftSlider) {
        elements.driftSlider.value = 100;
        elements.driftValue.textContent = '100%';
      }
      if (elements.glowSlider) {
        elements.glowSlider.value = 100;
        elements.glowValue.textContent = '100%';
      }
      if (elements.trailSlider) {
        elements.trailSlider.value = 1500;
        elements.trailValue.textContent = '1.5s';
      }
      if (elements.radiusSlider) {
        elements.radiusSlider.value = 100;
        elements.radiusValue.textContent = '100px';
      }
      if (elements.dotSizeSlider) {
        elements.dotSizeSlider.value = 100;
        elements.dotSizeValue.textContent = '100%';
      }

      updateBackgroundSettings();
    });
  }
} else {
  console.error('⚙️ Settings button not found!');
}

// Function to update background settings
function updateBackgroundSettings() {
  if (backgroundSystem.isEnabled) {
    // The background system will use these settings in its update loop

    // Update particle sizes if dot size changed
    if (backgroundSystem.updateParticleSizes) {
      backgroundSystem.updateParticleSizes();
    }
  }
}

// Initialize Three.js background
window.addEventListener('load', () => {
  if (typeof THREE === 'undefined') {
    console.error('Three.js not loaded! Background effects will not work.');
    return;
  }
  backgroundSystem.init();
});

// Tooltip system
function createTooltip(text) {
  const tooltip = document.createElement('div');
  tooltip.className = 'tooltip';
  tooltip.textContent = text;
  return tooltip;
}

function showTooltip(button, text) {
  const tooltipContainer = document.getElementById('tooltip-container');
  const tooltip = createTooltip(text);
  tooltipContainer.appendChild(tooltip);

  const rect = button.getBoundingClientRect();
  const tooltipHeight = 30;
  const arrowHeight = 5;

  // Position tooltip above the button
  tooltip.style.top = rect.top - tooltipHeight - arrowHeight - 8 + 'px';
  tooltip.style.left = rect.left + rect.width / 2 + 'px';
  tooltip.style.transform = 'translateX(-50%)';

  // Show tooltip
  setTimeout(() => tooltip.classList.add('show'), 10);

  return tooltip;
}

function hideTooltip(tooltip) {
  if (tooltip) {
    tooltip.classList.remove('show');
    setTimeout(() => {
      if (tooltip.parentNode) {
        tooltip.parentNode.removeChild(tooltip);
      }
    }, 200);
  }
}

// Add tooltip functionality to buttons
document.addEventListener('DOMContentLoaded', () => {
  const tooltipButtons = document.querySelectorAll('.audio-btn, .speed-btn, .help-btn');
  let currentTooltip = null;

  tooltipButtons.forEach((button) => {
    const tooltipText = button.getAttribute('data-tooltip');

    button.addEventListener('mouseenter', () => {
      if (tooltipText) {
        currentTooltip = showTooltip(button, tooltipText);
      }
    });

    button.addEventListener('mouseleave', () => {
      hideTooltip(currentTooltip);
      currentTooltip = null;
    });
  });
});

// Tooltip positioning
function updateTooltipPosition(button, tooltip, arrow) {
  const rect = button.getBoundingClientRect();
  const tooltipHeight = 30; // Approximate tooltip height
  const arrowHeight = 5;

  // Position tooltip above the button
  tooltip.style.top = rect.top - tooltipHeight - arrowHeight - 8 + 'px';
  tooltip.style.left = rect.left + rect.width / 2 + 'px';

  // Position arrow
  arrow.style.top = rect.top - arrowHeight - 8 + 'px';
  arrow.style.left = rect.left + rect.width / 2 + 'px';
}

// Add tooltip positioning to buttons
document.addEventListener('DOMContentLoaded', () => {
  const tooltipButtons = document.querySelectorAll('.audio-btn, .speed-btn, .help-btn');

  tooltipButtons.forEach((button) => {
    button.addEventListener('mouseenter', () => {
      const tooltip = button.querySelector('::before');
      const arrow = button.querySelector('::after');
      if (tooltip && arrow) {
        updateTooltipPosition(button, tooltip, arrow);
      }
    });
  });
});

// Gallery event listeners
document.addEventListener('DOMContentLoaded', function () {
  const closeBtn = document.getElementById('gallery-close');
  if (closeBtn) {
    closeBtn.addEventListener('click', () => ImageGalleryController.hideGallery());
  }

  const prevBtn = document.getElementById('gallery-prev');
  if (prevBtn) {
    prevBtn.addEventListener('click', () => ImageGalleryController.previousImage());
  }

  const nextBtn = document.getElementById('gallery-next');
  if (nextBtn) {
    nextBtn.addEventListener('click', () => ImageGalleryController.nextImage());
  }

  document.addEventListener('keydown', (e) => {
    if (!ImageGalleryController.isVisible) return;

    if (e.key === 'Escape') {
      ImageGalleryController.hideGallery();
    } else if (e.key === 'ArrowLeft') {
      ImageGalleryController.previousImage();
    } else if (e.key === 'ArrowRight') {
      ImageGalleryController.nextImage();
    }
  });
});

// Button click handler
function sendButtonClick(buttonId, buttonText) {
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(
      JSON.stringify({
        type: 'chat_message',
        data: { message: `[BUTTON_CLICK|${buttonId}|${buttonText}]` },
      })
    );
  } else {
    console.error('❌ WebSocket not connected, cannot send button click');
  }
}

// Handle incoming PM message
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
      messageHandler.addPrivateMessage(elements.privateChatBox, from, msg);
      // Clear unread status when user is actively viewing the chat
      clearUnreadStatus(from);
    } else {
      // Add unread status and notification
      addUnreadStatus(from);
      const tab = document.getElementById(`pm-tab-${from}`);
      if (tab) {
        tab.classList.add('notify');
        setTimeout(() => tab.classList.remove('notify'), 5000);
      }
    }
  } catch (error) {
    console.error('Error handling PM message:', error);
    if (currentPmUser === from) {
      messageHandler.addPrivateMessage(
        elements.privateChatBox,
        from,
        '[Encrypted message - decryption failed]'
      );
    }
  }
};

// Track unread messages per user
const unreadCounts = new Map();

// Add unread status to PM tab
function addUnreadStatus(user) {
  const tab = document.getElementById(`pm-tab-${user}`);
  if (!tab) return;

  // Only add unread status if:
  // 1. PM chat is minimized/hidden, OR
  // 2. User is not currently viewing this specific chat
  const isPmMinimized = elements.privateChatContainer.classList.contains('hidden');
  const isNotCurrentChat = currentPmUser !== user;

  if (isPmMinimized || isNotCurrentChat) {
    tab.classList.add('has-unread');

    // Increment unread count
    const currentCount = unreadCounts.get(user) || 0;
    const newCount = currentCount + 1;
    unreadCounts.set(user, newCount);

    // Get or create unread badge
    let badge = tab.querySelector('.unread-badge');
    if (!badge) {
      badge = document.createElement('div');
      badge.className = 'unread-badge';
      tab.appendChild(badge);
    }

    // Update badge count
    badge.textContent = newCount > 99 ? '99+' : newCount.toString();
  }
}

// Clear unread status from PM tab
function clearUnreadStatus(user) {
  const tab = document.getElementById(`pm-tab-${user}`);
  if (!tab) return;

  tab.classList.remove('has-unread');
  const badge = tab.querySelector('.unread-badge');
  if (badge) {
    badge.remove();
  }

  // Reset unread count
  unreadCounts.set(user, 0);
}
