// WebSocket Configuration
const WS_CONFIG = {
  LOCAL_WS_URL: `ws://${window.location.hostname}:8080/ws`,
  PRODUCTION_WS_URL: 'wss://chat.socksthoughtshop.lol/ws',
  // ACTIVE_WS_URL: `ws://${window.location.hostname}:8080/ws`,
  ACTIVE_WS_URL: `wss://chat.socksthoughtshop.lol/ws`,
  RECONNECT_DELAY: 1000, // Start with 1 second
  MAX_RECONNECT_DELAY: 30000, // Max 30 seconds
  PING_INTERVAL: 30000, // Send ping every 30 seconds
  PONG_TIMEOUT: 10000, // Wait 10 seconds for pong response
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

// WebSocket connection management
let reconnectAttempts = 0;
let reconnectTimer = null;
let pingTimer = null;
let pongTimer = null;
let isReconnecting = false;
let lastPongTime = Date.now();

// Background settings
const backgroundSettings = {
  dotSize: 1.2,
  brightness: 1.0,
  glowIntensity: 0.9,
  driftIntensity: 1.0,
  cursorRadius: 150,
  trailDuration: 600,
  decaySpeed: 1.0,
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
  infoToggle: document.getElementById('info-toggle'),
  infoPanel: document.getElementById('info-panel'),
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

  linkifyUrls(html) {
    // parse into a temporary document
    const doc = new DOMParser().parseFromString(html, 'text/html');
    // walk only text nodes
    const walker = doc.createTreeWalker(doc.body, NodeFilter.SHOW_TEXT, null, false);

    let node;
    while ((node = walker.nextNode())) {
      const text = node.nodeValue;
      const replaced = text.replace(
        /(https?:\/\/[^\s]+)/g,
        '<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>'
      );
      if (replaced !== text) {
        // replace text node with a span containing the new HTML
        const span = doc.createElement('span');
        span.innerHTML = replaced;
        node.parentNode.replaceChild(span, node);
      }
    }

    return doc.body.innerHTML;
  },
};

// Message handling
const messageHandler = {
  addMessage: (container, user, message, className = '') => {
    // Handle programming report command
    if (message.includes('[SHOW_PROGRAMMING_REPORT]')) {
      showProgrammingReportModal();
      message =
        message.replace('[SHOW_PROGRAMMING_REPORT]', '').trim() ||
        '📊 Showing detailed programming report...';
    }

    // Handle gallery commands
    const galleryMatch = message.match(/\[GALLERY_SHOW\|(.*?)\|([^|]+)\]/);
    if (galleryMatch) {
      const [fullMatch, imagesStr, title] = galleryMatch;
      const images = imagesStr.includes('||')
        ? imagesStr.split('||').map((img) => img.trim())
        : [imagesStr.trim()];

      // Only show gallery if we have valid images
      if (images.length > 0 && images[0].trim() !== '') {
        ImageGalleryController.showGallery(images, title);
        message =
          message.replace(fullMatch, '').trim() ||
          `📸 Showing ${images.length} image${images.length > 1 ? 's' : ''} for ${title}`;
      } else {
        // Remove the gallery command if no valid images
        message = message.replace(fullMatch, '').trim();
      }
    }

    // Handle YouTube gallery commands
    message = message.replace(/\[YOUTUBE_SHOW\|(.*?)\|([^|]+)\]/g, (_, videosStr, title) => {
      const videos = videosStr.includes('||')
        ? videosStr.split('||').map((video) => video.trim())
        : [videosStr.trim()];

      // Only create button if we have valid videos
      if (videos.length > 0 && videos[0].trim() !== '') {
        // Use base64 encoding to avoid JSON corruption from linkifyUrls
        const vidsJson = btoa(JSON.stringify(videos));

        const buttonId = `youtube-gallery-${Date.now()}`;

        return `<button 
            class="chat-button youtube-gallery-btn" 
            data-videos='${vidsJson}' 
            data-title='${title.replace(/'/g, '&#39;')}'
            data-button-id='${buttonId}'
          >
            🎥 View ${videos.length} YouTube Video${videos.length > 1 ? 's' : ''} for ${title}
          </button>`;
      } else {
        // Return empty string if no valid videos
        return '';
      }
    });

    // Linkify URLs after creating buttons
    message = utils.linkifyUrls(message);

    // Handle button commands
    message = message.replace(
      /\[BUTTON\|([^|]+)\|([^|]+)\]/g,
      '<button class="chat-button" onclick="sendButtonClick(\'$1\', \'$2\')">$2</button>'
    );

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
      // Reset TTS data for new response
      currentResponseTTS = null;

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

          // Only show gallery if we have valid images
          if (images.length > 0 && images[0].trim() !== '') {
            ImageGalleryController.showGallery(images, title);
            content =
              content.replace(fullMatch, '').trim() ||
              `📸 Showing ${images.length} image${images.length > 1 ? 's' : ''} for ${title}`;
          } else {
            // Remove the gallery command if no valid images
            content = content.replace(fullMatch, '').trim();
          }
        }

        // Handle YouTube gallery commands
        content = content.replace(/\[YOUTUBE_SHOW\|(.*?)\|([^|]+)\]/g, (_, videosStr, title) => {
          const videos = videosStr.includes('||')
            ? videosStr.split('||').map((video) => video.trim())
            : [videosStr.trim()];

          // Only create button if we have valid videos
          if (videos.length > 0 && videos[0].trim() !== '') {
            // Use base64 encoding to avoid JSON corruption from linkifyUrls
            const vidsJson = btoa(JSON.stringify(videos));

            const buttonId = `youtube-gallery-${Date.now()}`;

            return `<button 
                class="chat-button youtube-gallery-btn" 
                data-videos='${vidsJson}' 
                data-title='${title.replace(/'/g, '&#39;')}'
                data-button-id='${buttonId}'
              >
                🎥 View ${videos.length} YouTube Video${videos.length > 1 ? 's' : ''} for ${title}
              </button>`;
          } else {
            // Return empty string if no valid videos
            return '';
          }
        });

        // Linkify URLs after creating buttons
        content = utils.linkifyUrls(content);

        // Handle button commands
        content = content.replace(
          /\[BUTTON\|([^|]+)\|([^|]+)\]/g,
          '<button class="chat-button" onclick="sendButtonClick(\'$1\', \'$2\')">$2</button>'
        );
        messageText.innerHTML = content;
      }

      const cursor = streamingMessage.querySelector('.cursor-blink');
      if (cursor) cursor.remove();

      // Remove status indicator
      const statusIndicator = streamingMessage.querySelector('.streaming-status');
      if (statusIndicator) statusIndicator.remove();

      streamingMessage.classList.remove('streaming');
      streamingMessage.removeAttribute('id');
    } else {
      // Fallback for cached responses that don't have a streaming message
      // This handles the case where we receive a complete message without streaming context
      console.log('🔧 No streaming message found, creating new message for cached response');
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

  tts_response: (data) => {
    // Handle TTS response for cached responses
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

      // Play audio with iOS workaround
      const playAudio = async () => {
        try {
          await audio.play();
        } catch (err) {
          console.error('🔇 TTS play failed:', err);

          // iOS Safari workaround: Add play button
          if (isIOSSafari) {
            addPlayAudioButton(audio, data.voice_b64);
          }
        }
      };

      playAudio();

      // Add replay button to the last cached response message
      addTTSReplayButtonToCachedResponse(data.voice_b64);
    } else if (data.error) {
      console.error('❌ TTS error for cached response:', data.error);
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

      // If there was no streaming message to complete, create a new message for cached responses
      if (data.cached && data.full_message) {
        const existingMessage = elements.messages.querySelector('.message.bot:last-child');
        if (!existingMessage || !existingMessage.querySelector('.message-text')) {
          console.log('🔧 Creating new message for cached response');
          messageHandler.addMessage(elements.messages, data.user, data.full_message, 'bot');
        }
      }

      // Debug: Log all incoming data to understand the structure

      // Cache the complete response if we have the full message

      if (data.full_message && data.is_complete) {
        // Try to find the original question from recent messages
        const recentMessages = Array.from(elements.messages.children)
          .filter((msg) => msg.classList.contains('message') && !msg.classList.contains('bot'))
          .slice(-5) // Last 5 user messages
          .map((msg) => {
            const textElement = msg.querySelector('.message-text');
            return textElement ? textElement.textContent.trim() : '';
          })
          .filter((text) => text.length > 0);

        if (recentMessages.length > 0) {
          // Use the most recent user message as the question
          const question = recentMessages[recentMessages.length - 1];
          const cleanQuestion = question.replace(/@bot\s*/i, '').trim();

          // Cache system removed - no more local storage caching
          // Add timestamp to response
          const lastBotMessage = Array.from(elements.messages.children)
            .filter((msg) => msg.classList.contains('message') && msg.classList.contains('bot'))
            .pop();

          if (lastBotMessage && !lastBotMessage.querySelector('.generated-timestamp')) {
            // Check if this is a cached response
            const isCached = data.cached === true;
            const cachedModel = data.cached_model || null;
            addGeneratedTimestamp(lastBotMessage, currentResponseTTS, isCached, cachedModel);
            // Reset TTS data after using it
            currentResponseTTS = null;
          }
        } else {
        }
      }

      // ✅ Store TTS data for timestamp replay button
      if (data.voice_b64) {
        currentResponseTTS = data.voice_b64;
      }

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

        // Store the backend username as a data attribute for PM functionality
        li.innerHTML = `
        <span class="user-name" data-backend-username="${user}">${user}</span>
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

  display_name_change: (data) => {
    // Update the user's display name in the user list
    const userElements = document.querySelectorAll('.online-user .user-name');
    userElements.forEach((element) => {
      if (element.getAttribute('data-backend-username') === data.username) {
        element.textContent = data.displayName;
      }
    });
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
}

// WebSocket connection management functions
function clearTimers() {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  if (pingTimer) {
    clearInterval(pingTimer);
    pingTimer = null;
  }
  if (pongTimer) {
    clearTimeout(pongTimer);
    pongTimer = null;
  }
}

function startPingTimer() {
  if (pingTimer) {
    clearInterval(pingTimer);
  }

  pingTimer = setInterval(() => {
    if (socket && socket.readyState === WebSocket.OPEN) {
      try {
        socket.send(JSON.stringify({ type: 'ping' }));
        lastPongTime = Date.now();

        // Set pong timeout
        if (pongTimer) {
          clearTimeout(pongTimer);
        }
        pongTimer = setTimeout(() => {
          console.warn('⚠️ Pong timeout - connection may be stale');
          // Don't disconnect immediately, just log the warning
        }, WS_CONFIG.PONG_TIMEOUT);
      } catch (error) {
        console.error('❌ Failed to send ping:', error);
      }
    }
  }, WS_CONFIG.PING_INTERVAL);
}

function handleReconnect() {
  if (isReconnecting) return;

  isReconnecting = true;
  clearTimers();

  // Calculate exponential backoff delay
  const delay = Math.min(
    WS_CONFIG.RECONNECT_DELAY * Math.pow(2, reconnectAttempts),
    WS_CONFIG.MAX_RECONNECT_DELAY
  );

  console.log(`🔄 Attempting to reconnect in ${delay}ms (attempt ${reconnectAttempts + 1})`);

  reconnectTimer = setTimeout(() => {
    setupSocket();
  }, delay);

  reconnectAttempts++;
}

function resetReconnectAttempts() {
  reconnectAttempts = 0;
  isReconnecting = false;
}

// WebSocket setup
function setupSocket() {
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.close();
  }

  socket = new WebSocket(`${WS_CONFIG.ACTIVE_WS_URL}?token=${token}`);

  socket.addEventListener('open', () => {
    console.log('✅ WebSocket connected');
    elements.form.style.pointerEvents = 'auto';
    elements.form.style.opacity = '1';
    elements.connectingOverlay?.classList.add('hidden');

    // Reset reconnection state
    resetReconnectAttempts();

    // Start ping timer
    startPingTimer();
  });

  socket.addEventListener('message', (event) => {
    try {
      const data = JSON.parse(event.data);
      console.log('🔍 Received WebSocket message:', data);

      // Handle ping/pong
      if (data.type === 'ping') {
        // Respond to ping with pong
        if (socket && socket.readyState === WebSocket.OPEN) {
          socket.send(JSON.stringify({ type: 'pong' }));
        }
        return;
      }

      if (data.type === 'pong') {
        // Update last pong time
        lastPongTime = Date.now();
        if (pongTimer) {
          clearTimeout(pongTimer);
          pongTimer = null;
        }
        return;
      }

      if (data.type === 'error') {
        console.error('❌ Server error:', data.message);
        messageHandler.addMessage(elements.messages, 'System', `Error: ${data.message}`, 'system');
        return;
      }

      const handler = socketHandlers[data.event] || socketHandlers[data.type];
      if (handler) {
        handler(data.data || data);
      } else {
        console.warn('⚠️ No handler found for message type:', data.type || data.event);
        // Handle unknown message types gracefully
        if (data.message) {
          messageHandler.addMessage(elements.messages, 'System', data.message, 'system');
        } else if (typeof event.data === 'string') {
          messageHandler.addMessage(elements.messages, 'System', event.data, 'system');
        }
      }
    } catch (error) {
      console.error('Error parsing WebSocket message:', error);
      if (typeof event.data === 'string') {
        messageHandler.addMessage(elements.messages, 'System', event.data, 'bot');
      }
    }
  });

  socket.addEventListener('error', (error) => {
    console.error('❌ WebSocket error:', error);
    elements.connectingOverlay.innerHTML =
      '<div class="username-form"><h2>Connection failed. Trying to reconnect...</h2></div>';
  });

  socket.addEventListener('close', (event) => {
    console.log(`🔌 WebSocket closed: ${event.code} - ${event.reason}`);
    clearTimers();

    // Don't reconnect if it was a normal closure
    if (event.code === 1000 || event.code === 1001) {
      console.log('✅ Normal WebSocket closure');
      return;
    }

    // Attempt to reconnect
    handleReconnect();
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
  sendSocketMessage({ type: 'pm_decline', to: user });
  toast.remove();
}

function sendPmInvite(user) {
  ensurePmFooterTab(user, user, 'pending');
  sendSocketMessage({ type: 'pm_invite', to: user });
  requestPublicKey(user);
}

function requestPublicKey(username) {
  sendSocketMessage({ type: 'pubkey_request', to: username });
}

async function sendPublicKey(username) {
  try {
    const publicKeyString = await utils.exportPublicKey(keyPair.publicKey);
    sendSocketMessage({ type: 'pubkey_response', to: username, public_key: publicKeyString });
  } catch (error) {
    console.error(`Error sending public key to ${username}:`, error);
  }
}

function acceptPmInvite(user, toast) {
  try {
    sendSocketMessage({ type: 'pm_accept', to: user });
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
      const success = sendSocketMessage({ type: 'pm_message', to, ciphertext });

      if (success) {
        messageHandler.addPrivateMessage(elements.privateChatBox, currentUsername, msg);
        elements.privateInput.value = '';
      }
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
    sendSocketMessage({ type: 'pm_disconnect', to: currentUser });

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
    elements.usersToggle.classList.add('panel-hidden');
    elements.usersToggle.textContent = '👥';
    elements.usersToggle.title = 'Show Users Panel';
  } else {
    elements.usersPanel.classList.add('panel-loading');
    elements.usersPanel.classList.remove('hidden');
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

// Info panel toggle
function toggleInfoPanel() {
  const isInfoPanelHidden = elements.infoPanel.classList.contains('hidden');

  if (isInfoPanelHidden) {
    elements.infoPanel.classList.remove('hidden');
    elements.infoToggle.classList.remove('panel-hidden');
    elements.infoToggle.textContent = '◀';
    elements.infoToggle.title = 'Hide Info Panel';
  } else {
    elements.infoPanel.classList.add('hidden');
    elements.infoToggle.classList.add('panel-hidden');
    elements.infoToggle.textContent = '▶';
    elements.infoToggle.title = 'Show Info Panel';
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

// Programming Report Modal Functions
function showProgrammingReportModal() {
  const modal = document.getElementById('programming-report-modal');
  modal?.classList.remove('hidden');
  document.body.classList.add('modal-open');
}

function hideProgrammingReportModal() {
  const modal = document.getElementById('programming-report-modal');
  modal?.classList.add('hidden');
  document.body.classList.remove('modal-open');
}

function setupProgrammingReportModalHandlers() {
  const closeBtn = document.getElementById('programming-report-close');
  const modal = document.getElementById('programming-report-modal');

  closeBtn?.addEventListener('click', hideProgrammingReportModal);

  // Close modal when clicking outside
  modal?.addEventListener('click', (e) => {
    if (e.target === modal) {
      hideProgrammingReportModal();
    }
  });

  // Close modal with Escape key
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !modal?.classList.contains('hidden')) {
      hideProgrammingReportModal();
    }
  });
}

// Make the function globally available for bot responses
window.showProgrammingReportModal = showProgrammingReportModal;

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

// YouTube Gallery Controller
const YouTubeGalleryController = {
  currentVideos: [],
  currentIndex: 0,
  isVisible: false,

  showGalleryFromButton(buttonId, videosJson, title = 'YouTube Videos') {
    console.log('showGalleryFromButton', buttonId, videosJson, title);
    // Parse the videos JSON string back to an array
    let videos;
    try {
      // Try to decode base64 first (new method)
      try {
        const decodedJson = atob(videosJson);
        videos = JSON.parse(decodedJson);
      } catch (base64Error) {
        // Fallback to old method for backward compatibility
        let cleanJson = videosJson
          .replace(/&quot;/g, '"')
          .replace(/&#39;/g, "'")
          .replace(/&amp;/g, '&')
          .replace(/&lt;/g, '<')
          .replace(/&gt;/g, '>');

        // Additional cleanup for common JSON corruption issues
        cleanJson = cleanJson.trim();

        // If the JSON is still malformed, try to extract just the array part
        if (!cleanJson.startsWith('[')) {
          const match = cleanJson.match(/\[.*\]/);
          if (match) {
            cleanJson = match[0];
          }
        }

        videos = JSON.parse(cleanJson);
      }
    } catch (error) {
      console.error('Error parsing videos JSON:', error);
      console.error('Raw videosJson:', videosJson);
      return;
    }

    // Use the same container as the image gallery
    const container = document.getElementById('image-gallery-container');
    const titleElement = document.getElementById('gallery-title');
    const imagesContainer = document.getElementById('gallery-images');

    if (!container || !imagesContainer) {
      console.error('Image gallery container not found');
      return;
    }

    this.currentVideos = videos;
    this.currentIndex = 0;
    this.isVisible = true;

    titleElement.textContent = title;
    imagesContainer.innerHTML = '';

    videos.forEach((videoUrl, index) => {
      const videoId = this.extractVideoId(videoUrl);
      if (videoId) {
        const videoDiv = document.createElement('div');
        videoDiv.className = index === 0 ? 'youtube-video active' : 'youtube-video';
        videoDiv.style.display = index === 0 ? 'block' : 'none';
        videoDiv.style.margin = '0';
        videoDiv.style.padding = '0';
        videoDiv.style.width = '100%';
        videoDiv.style.height = '100%';
        videoDiv.innerHTML = `
          <iframe 
            width="100%" 
            height="315" 
            src="https://www.youtube.com/embed/${videoId}" 
            frameborder="0" 
            style="margin: 0; padding: 0; border: none;"
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" 
            allowfullscreen>
          </iframe>
        `;
        imagesContainer.appendChild(videoDiv);
      }
    });

    this.updateCounter();
    this.updateNavButtons();
    container.classList.remove('hidden');
  },

  showGallery(videos, title = 'YouTube Videos') {
    // Legacy method - redirect to the new button-based method
    this.showGalleryFromButton('legacy', videos, title);
  },

  createYouTubeGalleryContainer() {
    // Create the container if it doesn't exist
    const existingContainer = document.getElementById('youtube-gallery-container');
    if (existingContainer) return;

    const container = document.createElement('div');
    container.id = 'youtube-gallery-container';
    container.className = 'gallery-container hidden';
    container.innerHTML = `
      <div class="gallery-overlay">
        <div class="gallery-content">
          <div class="gallery-header">
            <h3 id="youtube-gallery-title">YouTube Videos</h3>
            <button class="gallery-close" onclick="YouTubeGalleryController.hideGallery()">×</button>
          </div>
          <div id="youtube-gallery-videos" class="gallery-videos"></div>
          <div class="gallery-footer">
            <button id="youtube-gallery-prev" class="gallery-nav-btn" onclick="YouTubeGalleryController.previousVideo()">‹</button>
            <span id="youtube-gallery-counter" class="gallery-counter">1 of 1</span>
            <button id="youtube-gallery-next" class="gallery-nav-btn" onclick="YouTubeGalleryController.nextVideo()">›</button>
          </div>
        </div>
      </div>
    `;
    document.body.appendChild(container);
  },

  extractVideoId(url) {
    // Extract video ID from various YouTube URL formats
    const patterns = [
      /(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([a-zA-Z0-9_-]+)/,
      /youtube\.com\/watch\?.*v=([a-zA-Z0-9_-]+)/,
    ];

    for (const pattern of patterns) {
      const match = url.match(pattern);
      if (match) {
        return match[1];
      }
    }
    return null;
  },

  hideGallery() {
    const container = document.getElementById('image-gallery-container');
    if (container) {
      container.classList.add('hidden');
      this.isVisible = false;
      this.currentVideos = [];
      this.currentIndex = 0;
    }
  },

  nextVideo() {
    if (this.currentVideos.length <= 1) return;

    const videos = document.querySelectorAll('#gallery-images .youtube-video');
    if (videos.length === 0) return;

    videos[this.currentIndex].classList.remove('active');
    videos[this.currentIndex].style.display = 'none';
    this.currentIndex = (this.currentIndex + 1) % this.currentVideos.length;
    videos[this.currentIndex].classList.add('active');
    videos[this.currentIndex].style.display = 'block';
    this.updateCounter();
    this.updateNavButtons();
  },

  previousVideo() {
    if (this.currentVideos.length <= 1) return;

    const videos = document.querySelectorAll('#gallery-images .youtube-video');
    if (videos.length === 0) return;

    videos[this.currentIndex].classList.remove('active');
    videos[this.currentIndex].style.display = 'none';
    this.currentIndex =
      this.currentIndex === 0 ? this.currentVideos.length - 1 : this.currentIndex - 1;
    videos[this.currentIndex].classList.add('active');
    videos[this.currentIndex].style.display = 'block';
    this.updateCounter();
    this.updateNavButtons();
  },

  updateCounter() {
    const counter = document.getElementById('gallery-counter');
    if (counter && this.currentVideos.length > 0) {
      counter.textContent = `${this.currentIndex + 1} of ${this.currentVideos.length}`;
    }
  },

  updateNavButtons() {
    const prevBtn = document.getElementById('gallery-prev');
    const nextBtn = document.getElementById('gallery-next');
    if (prevBtn && nextBtn) {
      const hasMultipleVideos = this.currentVideos.length > 1;
      prevBtn.disabled = !hasMultipleVideos;
      nextBtn.disabled = !hasMultipleVideos;
    }
  },
};

const backgroundSystem = {
  scene: null,
  camera: null,
  renderer: null,
  instancedMesh: null,
  mouseX: 0,
  mouseY: 0,
  isEnabled: false,
  instanceCount: 0,
  dummy: new THREE.Object3D(),
  tempColor: new THREE.Color(),

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
    const gridWidth = 90;
    const gridHeight = 50;
    const spacingX = 15;
    const spacingY = 15;
    const depthRange = 350;
    const baseSize = 1 * backgroundSettings.dotSize;

    const startX = -(gridWidth * spacingX) / 2;
    const startY = -(gridHeight * spacingY) / 2;

    const geometry = new THREE.CircleGeometry(baseSize, 8);
    const material = new THREE.ShaderMaterial({
      transparent: true,
      vertexShader: `
        attribute vec3 instanceColor;
        attribute float instanceOpacity;
        varying vec3 vColor;
        varying float vOpacity;
    
        void main() {
          vColor = instanceColor;
          vOpacity = instanceOpacity;
          vec4 mvPosition = modelViewMatrix * instanceMatrix * vec4(position, 1.0);
          gl_Position = projectionMatrix * mvPosition;
        }
      `,
      fragmentShader: `
        varying vec3 vColor;
        varying float vOpacity;
    
        void main() {
          gl_FragColor = vec4(vColor, vOpacity);
        }
      `,
    });

    this.instanceCount = gridWidth * gridHeight;
    this.instancedMesh = new THREE.InstancedMesh(geometry, material, this.instanceCount);
    const instanceColorBuffer = new THREE.InstancedBufferAttribute(
      new Float32Array(this.instanceCount * 3),
      3
    );
    const instanceOpacityBuffer = new THREE.InstancedBufferAttribute(
      new Float32Array(this.instanceCount),
      1
    );
    this.instancedMesh.geometry.setAttribute('instanceColor', instanceColorBuffer);
    this.instancedMesh.geometry.setAttribute('instanceOpacity', instanceOpacityBuffer);

    this.instanceData = [];

    let index = 0;
    for (let x = 0; x < gridWidth; x++) {
      for (let y = 0; y < gridHeight; y++) {
        const posX = startX + x * spacingX;
        const posY = startY + y * spacingY;
        const depthProgress = (gridHeight - 1 - y) / (gridHeight - 1);
        const posZ = depthRange * (depthProgress - 0.8);

        this.instanceData.push({
          basePos: new THREE.Vector3(posX, posY, posZ),
          opacity: 0.15,
          color: new THREE.Color(1, 1, 1),
          lastGlowTime: 0,
        });

        // Initial transform
        this.dummy.position.copy(this.instanceData[index].basePos);
        this.dummy.scale.set(1, 1, 1);
        this.dummy.updateMatrix();
        this.instancedMesh.setMatrixAt(index, this.dummy.matrix);

        // Set initial color and opacity in the attributes
        const colorArray = this.instancedMesh.geometry.attributes.instanceColor.array;
        const opacityArray = this.instancedMesh.geometry.attributes.instanceOpacity.array;
        colorArray[index * 3] = 1.0; // R
        colorArray[index * 3 + 1] = 1.0; // G
        colorArray[index * 3 + 2] = 1.0; // B
        opacityArray[index] = 0.15; // Initial opacity

        index++;
      }
    }

    this.instancedMesh.instanceMatrix.needsUpdate = true;
    this.instancedMesh.geometry.attributes.instanceColor.needsUpdate = true;
    this.instancedMesh.geometry.attributes.instanceOpacity.needsUpdate = true;

    this.scene.add(this.instancedMesh);
  },

  addEventListeners() {
    document.addEventListener(
      'mousemove',
      (e) => {
        this.mouseX = e.clientX;
        this.mouseY = e.clientY;
      },
      { passive: true }
    );

    window.addEventListener(
      'resize',
      () => {
        this.camera.aspect = window.innerWidth / window.innerHeight;
        this.camera.updateProjectionMatrix();
        this.renderer.setSize(window.innerWidth, window.innerHeight);
      },
      { passive: true }
    );
  },

  updateParticles() {
    if (!this.isEnabled) return;

    const now = Date.now();
    const time = now * 0.001;
    const driftX = Math.sin(time * 0.25) * 8 * backgroundSettings.driftIntensity;
    const driftY = Math.cos(time * 0.25) * 6 * backgroundSettings.driftIntensity;
    const driftZ = Math.sin(time * 0.2) * 3 * backgroundSettings.driftIntensity;

    const cursorRadius = backgroundSettings.cursorRadius;
    const trailDuration = backgroundSettings.trailDuration;
    const lerpSpeed = 0.02 * backgroundSettings.decaySpeed;

    for (let i = 0; i < this.instanceCount; i++) {
      const data = this.instanceData[i];

      const currentX = data.basePos.x + driftX;
      const currentY = data.basePos.y + driftY;
      const currentZ = data.basePos.z + driftZ;

      this.dummy.position.set(currentX, currentY, currentZ);
      this.dummy.scale.set(1, 1, 1);
      this.dummy.updateMatrix();
      this.instancedMesh.setMatrixAt(i, this.dummy.matrix);

      const vector = new THREE.Vector3(currentX, currentY, currentZ);
      vector.project(this.camera);
      const screenX = (vector.x * 0.5 + 0.5) * window.innerWidth;
      const screenY = (-vector.y * 0.5 + 0.5) * window.innerHeight;

      let targetOpacity = 0.15 * backgroundSettings.brightness;
      let targetColor = this.tempColor.setRGB(1, 1, 1);

      const distance = Math.sqrt((this.mouseX - screenX) ** 2 + (this.mouseY - screenY) ** 2);
      if (distance <= cursorRadius) {
        const intensity = 1 - distance / cursorRadius;
        targetOpacity += intensity * 1.2 * backgroundSettings.glowIntensity;
        targetColor = this.tempColor.setRGB(1, 0.42, 0.42);
        data.lastGlowTime = now;
      } else {
        const timeSinceGlow = now - (data.lastGlowTime || 0);
        if (timeSinceGlow < trailDuration) {
          const trailIntensity = 1 - timeSinceGlow / trailDuration;
          targetOpacity += trailIntensity * 0.8 * backgroundSettings.glowIntensity;
        }
      }

      // Lerp opacity and color
      data.opacity = THREE.MathUtils.lerp(data.opacity, targetOpacity, lerpSpeed);
      data.color.lerp(targetColor, lerpSpeed);

      // Update the instanceColor and instanceOpacity attributes manually
      const colorArray = this.instancedMesh.geometry.attributes.instanceColor.array;
      const opacityArray = this.instancedMesh.geometry.attributes.instanceOpacity.array;
      colorArray[i * 3] = data.color.r; // R
      colorArray[i * 3 + 1] = data.color.g; // G
      colorArray[i * 3 + 2] = data.color.b; // B
      opacityArray[i] = data.opacity; // Opacity
    }

    this.instancedMesh.instanceMatrix.needsUpdate = true;
    this.instancedMesh.geometry.attributes.instanceColor.needsUpdate = true;
    this.instancedMesh.geometry.attributes.instanceOpacity.needsUpdate = true;
  },

  startRenderLoop() {
    const animate = () => {
      if (this.isEnabled) {
        this.updateParticles();
        this.renderer.render(this.scene, this.camera);
        requestAnimationFrame(animate);
      }
    };
    if (!this.renderLoopStarted) {
      this.renderLoopStarted = true;
      requestAnimationFrame(animate);
    }
  },

  disable() {
    this.isEnabled = false;
    this.renderLoopStarted = false;
  },
};

// Initialize app
window.addEventListener('DOMContentLoaded', () => {
  // Check for token in cookie
  token = utils.getTokenFromCookie('access_token');

  // If no token, just proceed - the server will handle it
  if (!token) {
  }

  initializeApp();

  // Cache stats are now only updated when the cache manager modal is opened

  // Show tutorial sequence on page load
  setTimeout(() => {
    startTutorialSequence();
  }, 1000);

  // Add event listener for YouTube gallery buttons
  document.addEventListener('click', (event) => {
    if (event.target.classList.contains('youtube-gallery-btn')) {
      const videosJson = event.target.getAttribute('data-videos');
      const title = event.target.getAttribute('data-title');
      const buttonId = event.target.getAttribute('data-button-id');

      if (videosJson && title) {
        YouTubeGalleryController.showGalleryFromButton(buttonId, videosJson, title);
      }
    }
  });
});

function initializeApp() {
  // If no token, use a default guest username
  if (!token) {
    currentUsername = 'guest_' + Math.random().toString(36).substr(2, 8);
  } else {
    const payload = utils.parseJwt(token);
    if (!payload?.sub) {
      console.error('Invalid token, using default guest username');
      currentUsername = 'guest_' + Math.random().toString(36).substr(2, 8);
    } else {
      currentUsername = payload.sub;
    }
  }

  // Display name logic
  window.displayName = currentUsername;
  const userDisplay = document.getElementById('current-user');
  const editBtn = document.getElementById('edit-username-btn');
  const input = document.getElementById('edit-username-input');
  const saveBtn = document.getElementById('save-username-btn');
  const cancelBtn = document.getElementById('cancel-username-btn');

  function updateDisplayName(name) {
    window.displayName = name;
    userDisplay.textContent = displayName;
    // Cache system removed - no more local storage caching

    // Broadcast display name change to other users
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(
        JSON.stringify({
          type: 'display_name_change',
          data: {
            displayName: name,
            username: currentUsername,
          },
        })
      );
    }
  }

  updateDisplayName(displayName);

  editBtn.addEventListener('click', () => {
    input.value = displayName;
    input.style.display = 'inline-block';
    saveBtn.style.display = 'inline-block';
    cancelBtn.style.display = 'inline-block';
    editBtn.style.display = 'none';
    userDisplay.style.display = 'none';
    input.focus();
  });

  saveBtn.addEventListener('click', () => {
    const newName = input.value.trim().slice(0, 24);
    if (newName) {
      updateDisplayName(newName);
    }
    input.style.display = 'none';
    saveBtn.style.display = 'none';
    cancelBtn.style.display = 'none';
    editBtn.style.display = 'inline-block';
    userDisplay.style.display = 'inline-block';
  });

  cancelBtn.addEventListener('click', () => {
    input.style.display = 'none';
    saveBtn.style.display = 'none';
    cancelBtn.style.display = 'none';
    editBtn.style.display = 'inline-block';
    userDisplay.style.display = 'inline-block';
  });

  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') saveBtn.click();
    if (e.key === 'Escape') cancelBtn.click();
  });

  // Track user interactions for iOS audio compatibility
  const markUserInteraction = () => {
    if (!userHasInteracted) {
      userHasInteracted = true;

      // Try to play any pending audio
      if (pendingAudio) {
        pendingAudio.play().catch((err) => {});
        pendingAudio = null;
      } else if (currentAudio && currentAudio.paused) {
        currentAudio.play().catch((err) => {
          // Audio play failed
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
    window.location.href = '/';
  });

  elements.privateSendBtn.addEventListener('click', sendPrivateMessage);
  elements.privateChatClose.addEventListener('click', closePrivateChat);
  elements.privateChatMinimize.addEventListener('click', minimizePrivateChat);
  elements.privateChatMaximize.addEventListener('click', maximizePrivateChat);
  elements.privateInput.addEventListener('keypress', handlePrivateInputKeyPress);
  elements.usersToggle?.addEventListener('click', toggleUsersPanel);
  elements.infoToggle?.addEventListener('click', toggleInfoPanel);

  setupHelpModalHandlers();
  setupProgrammingReportModalHandlers();

  elements.usersPanel.classList.add('hidden');
  elements.mainContainer.classList.add('panel-hidden');
  elements.usersToggle.classList.add('panel-hidden');
  elements.usersToggle.textContent = '👥';
  elements.usersToggle.title = 'Show Users Panel';

  // Initialize info panel
  elements.infoPanel.classList.add('hidden');
  elements.infoToggle.classList.add('panel-hidden');
  elements.infoToggle.textContent = '▶';
  elements.infoToggle.title = 'Show Info Panel';

  // Only generate RSA key pair if Web Crypto API is available (HTTPS or localhost)
  if (utils.isCryptoAvailable()) {
    utils.generateKeyPair().catch((error) => {
      console.error('Failed to generate RSA key pair:', error);
    });
  } else {
    // Web Crypto API not available
  }

  elements.connectingOverlay?.classList.remove('hidden');
  setupSocket();

  setTimeout(() => {
    elements.usersPanel?.classList.remove('panel-loading');
  }, 100);
}

// Safe message sending function
function sendSocketMessage(message) {
  if (!socket || socket.readyState !== WebSocket.OPEN) {
    console.warn('⚠️ WebSocket not connected, cannot send message');
    messageHandler.addMessage(
      elements.messages,
      'System',
      'Connection lost. Trying to reconnect...',
      'system'
    );
    handleReconnect();
    return false;
  }

  try {
    const messageStr = JSON.stringify(message);
    console.log('🔍 Sending WebSocket message:', messageStr);
    socket.send(messageStr);
    return true;
  } catch (error) {
    console.error('❌ Failed to send message:', error);
    messageHandler.addMessage(
      elements.messages,
      'System',
      'Failed to send message. Trying to reconnect...',
      'system'
    );
    handleReconnect();
    return false;
  }
}

// Chat form submission
elements.form.addEventListener('submit', (e) => {
  e.preventDefault();

  let message = elements.input.value.trim();
  if (message && currentUsername) {
    if (
      elements.botToggle.classList.contains('active') &&
      !message.toLowerCase().startsWith('@bot')
    ) {
      message = '@bot ' + message;
    }

    // Check if this is a bot message that we can cache
    const isBotMessage =
      message.toLowerCase().includes('@bot') || elements.botToggle.classList.contains('active');

    if (isBotMessage) {
      // Clean the message for caching (remove @bot prefix)
      const cleanMessage = message.replace(/@bot\s*/i, '').trim();

      // Check cache first (unless we're generating a new response)
    }

    const success = sendSocketMessage({
      type: 'chat_message',
      data: {
        message,
        displayName: window.displayName || currentUsername,
      },
    });

    if (success) {
      elements.input.value = '';
    }
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
  elements.volumeSlider.addEventListener(
    'touchstart',
    (e) => {
      e.stopPropagation();
    },
    { passive: true }
  );

  elements.volumeSlider.addEventListener(
    'touchmove',
    (e) => {
      e.stopPropagation();
    },
    { passive: true }
  );

  elements.volumeSlider.addEventListener(
    'touchend',
    (e) => {
      e.stopPropagation();
    },
    { passive: true }
  );
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
  elements.speedToggle.addEventListener(
    'wheel',
    (e) => {
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
    },
    { passive: false }
  );

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

  elements.speedToggle.addEventListener(
    'touchcancel',
    (e) => {
      e.preventDefault();

      // Remove visual feedback if touch is cancelled
      elements.speedToggle.classList.remove('touch-active');
    },
    { passive: false }
  );
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

  // Cache button functionality
  const cacheBtn = document.getElementById('cache-btn');
  if (cacheBtn) {
    cacheBtn.addEventListener('click', (e) => {
      e.preventDefault();
      showCacheManager();
    });
  }

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
    closeBtn.addEventListener('click', () => {
      // Check if we're showing YouTube videos or images
      const hasYouTubeVideos =
        document.querySelectorAll('#gallery-images .youtube-video').length > 0;
      if (hasYouTubeVideos) {
        YouTubeGalleryController.hideGallery();
      } else {
        ImageGalleryController.hideGallery();
      }
    });
  }

  const prevBtn = document.getElementById('gallery-prev');
  if (prevBtn) {
    prevBtn.addEventListener('click', () => {
      // Check if we're showing YouTube videos or images
      const hasYouTubeVideos =
        document.querySelectorAll('#gallery-images .youtube-video').length > 0;
      if (hasYouTubeVideos) {
        YouTubeGalleryController.previousVideo();
      } else {
        ImageGalleryController.previousImage();
      }
    });
  }

  const nextBtn = document.getElementById('gallery-next');
  if (nextBtn) {
    nextBtn.addEventListener('click', () => {
      // Check if we're showing YouTube videos or images
      const hasYouTubeVideos =
        document.querySelectorAll('#gallery-images .youtube-video').length > 0;
      if (hasYouTubeVideos) {
        YouTubeGalleryController.nextVideo();
      } else {
        ImageGalleryController.nextImage();
      }
    });
  }

  document.addEventListener('keydown', (e) => {
    const isImageGalleryVisible = ImageGalleryController.isVisible;
    const isYouTubeGalleryVisible = YouTubeGalleryController.isVisible;

    if (!isImageGalleryVisible && !isYouTubeGalleryVisible) return;

    if (e.key === 'Escape') {
      if (isYouTubeGalleryVisible) {
        YouTubeGalleryController.hideGallery();
      } else {
        ImageGalleryController.hideGallery();
      }
    } else if (e.key === 'ArrowLeft') {
      const hasYouTubeVideos =
        document.querySelectorAll('#gallery-images .youtube-video').length > 0;
      if (hasYouTubeVideos) {
        YouTubeGalleryController.previousVideo();
      } else {
        ImageGalleryController.previousImage();
      }
    } else if (e.key === 'ArrowRight') {
      const hasYouTubeVideos =
        document.querySelectorAll('#gallery-images .youtube-video').length > 0;
      if (hasYouTubeVideos) {
        YouTubeGalleryController.nextVideo();
      } else {
        ImageGalleryController.nextImage();
      }
    }
  });
});

// Button click handler
function sendButtonClick(buttonId, buttonText) {
  const message = {
    type: 'chat_message',
    data: {
      message: `[BUTTON_CLICK|${buttonId}|${buttonText}]`,
      displayName: window.displayName || currentUsername,
    },
  };
  console.log('🔍 Sending button click message:', message);
  sendSocketMessage(message);
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

// Enhanced tutorial positioning using getBoundingClientRect()
class TutorialPositioner {
  constructor() {
    this.currentToast = null;
    this.currentArrow = null;
    const marker = document.createElementNS('http://www.w3.org/2000/svg', 'marker');

    // Give the marker an internal coordinate system that matches your polygon's raw points
    marker.setAttribute('viewBox', '0 0 10 7');

    // Tell SVG to interpret markerWidth/markerHeight in user-space units (pixels)
    marker.setAttribute('markerUnits', 'userSpaceOnUse');

    // Now set the on-screen size you actually want, e.g. 40×28px:
    marker.setAttribute('markerWidth', '40');
    marker.setAttribute('markerHeight', '28');

    // Re-anchor the "tip" point inside that box (half of height, plus any horizontal offset)
    marker.setAttribute('refX', '10');
    marker.setAttribute('refY', '3.5');

    marker.setAttribute('orient', 'auto');

    // Draw the shape in its own 0–10 × 0–7 coordinate space
    const polygon = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
    polygon.setAttribute('points', '0 0, 10 3.5, 0 7');
    polygon.setAttribute('fill', 'rgba(219, 52, 52, 0.8)');

    marker.appendChild(polygon);
  }

  // Get the center coordinates of an element
  getElementCenter(selector) {
    const element = document.querySelector(selector);
    if (!element) {
      return null;
    }

    const rect = element.getBoundingClientRect();
    const center = {
      centerX: rect.left + rect.width / 2,
      centerY: rect.top + rect.height / 2,
      rect: rect,
    };

    return center;
  }

  // Show a simple toast at a target element
  showTutorialToast(
    message,
    targetSelector,
    options = {},
    subStep = false,
    isInArray = false,
    firstSubStepPosition = null
  ) {
    console.log(
      'Tutorial: showTutorialToast called with subStep=',
      subStep,
      'currentToast exists=',
      !!this.currentToast,
      'isInArray=',
      isInArray
    );
    const {
      position = 'top',
      preferredSide = null,
      offset = { x: 0, y: 0 },
      duration = 3000,
      type = 'info',
      fontSize = '16px',
      autoRemove = true,
    } = options;

    if (subStep && this.currentToast) {
      // Sub-step - updating existing toast, no timer
      // For sub-steps, just update the message and arrow, don't move the toast
      this.currentToast.querySelector('.tutorial-content').textContent = message;

      // For sub-steps, don't change the arrow orientation - just update the target
      // Keep the same arrow direction throughout the entire array
      this.updateArrowTarget(targetSelector, offset);

      // Don't set auto-remove timer for sub-steps - let the parent handle timing

      return this.currentToast;
    }

    // Remove any existing toast
    this.removeCurrentToast();

    // Create toast container
    this.currentToast = document.createElement('div');
    this.currentToast.className = `tutorial-toast ${type}`;
    this.currentToast.innerHTML = `
      <div class="tutorial-content">${message}</div>
    `;
    // Add keyframes for the glow animation
    const glowKeyframes = `
      @keyframes borderGlow {
        0% { box-shadow: 0 8px 32px rgba(0,0,0,0.30), 0 0 15px rgba(0, 150, 255, 0.8), 0 0 25px rgba(100, 50, 200, 0.6); }
        50% { box-shadow: 0 8px 32px rgba(0,0,0,0.30), 0 0 20px rgba(50, 0, 150, 0.9), 0 0 30px rgba(0, 100, 255, 0.7); }
        100% { box-shadow: 0 8px 32px rgba(0,0,0,0.30), 0 0 15px rgba(0, 150, 255, 0.8), 0 0 25px rgba(100, 50, 200, 0.6); }
      }
    `;
    const styleSheet = document.createElement('style');
    styleSheet.textContent = glowKeyframes;
    document.head.appendChild(styleSheet);

    Object.assign(this.currentToast.style, {
      fontSize, // your dynamic size e.g. '14px'
      background: 'rgba(0, 0, 0, 0.7)', // dark background
      backdropFilter: 'blur(20px)', // heavy blur
      WebkitBackdropFilter: 'blur(20px)', // safari support
      boxShadow:
        'inset 0 0 0 1px rgba(255,255,255,0.1),' + // subtle white inner border
        '0 8px 32px rgba(0,0,0,0.40),' + // stronger dark shadow
        '0 0 15px rgba(0, 150, 255, 0.8),' + // cool blue glow
        '0 0 25px rgba(100, 50, 200, 0.6)', // dark purple glow
      borderRadius: '16px', // rounded corners
      padding: '16px 24px', // roomy padding
      color: '#ffffff', // pure white text
      textShadow: '0 1px 2px rgba(0,0,0,0.8)', // stronger text shadow
      cursor: 'pointer',
      transition: 'transform 0.2s ease, opacity 0.3s ease',
      animation: 'bounceIn 0.6s ease-out, borderGlow 3s ease-in-out infinite',
      border: '2px solid rgba(0, 150, 255, 0.6)',
    });

    // (Then append to the DOM as before)
    document.body.appendChild(this.currentToast);

    // Optional: trigger a subtle hover "pop"
    this.currentToast.addEventListener('mouseenter', () => {
      this.currentToast.style.transform = 'scale(1.04)';
    });
    this.currentToast.addEventListener('mouseleave', () => {
      this.currentToast.style.transform = 'scale(1)';
    });

    // Add to document first so we can get proper dimensions
    document.body.appendChild(this.currentToast);

    // Position the toast relative to the target (after it's in the DOM)
    this.positionToast(targetSelector, position, offset, preferredSide, false);

    // Auto-remove after duration (but not for any sub-steps or array items)
    if (autoRemove && !subStep && !isInArray) {
      // Setting auto-remove timer
      setTimeout(() => {
        // Auto-remove timer fired, removing toast
        this.removeCurrentToast();
      }, duration);
    } else if (subStep || isInArray) {
      // Sub-step or array item - no auto-remove timer set
    }

    return this.currentToast;
  }

  // Calculate optimal position based on target location in viewport
  calculateOptimalPosition(targetSelector, offset, preferredSide = null) {
    const center = this.getElementCenter(targetSelector);
    if (!center) return null;

    const toastRect = this.currentToast.getBoundingClientRect();
    const targetRect = center.rect;
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;
    const toastLeftEdge = toastRect.left;
    const toastRightEdge = toastRect.right;
    const toastTopEdge = toastRect.top;
    const toastBottomEdge = toastRect.bottom;

    // Calculate available space in each direction
    const spaceAbove = targetRect.top;
    const spaceBelow = viewportHeight - targetRect.bottom;
    const spaceLeft = targetRect.left;
    const spaceRight = viewportWidth - targetRect.right;

    // Determine best position based on available space
    let position, left, top;

    // If preferredSide is specified, try to use it first
    if (preferredSide) {
      switch (preferredSide) {
        case 'top':
          if (spaceAbove >= toastRect.height + 20) {
            position = 'top';
            left = center.centerX - toastRect.width / 2 + offset.x;
            top = targetRect.top - toastRect.height - 30 + offset.y;
          }
          break;
        case 'bottom':
          if (spaceBelow >= toastRect.height + 20) {
            position = 'bottom';
            left = center.centerX - toastRect.width / 2 + offset.x;
            top = targetRect.bottom + 30 + offset.y;
          }
          break;
        case 'left':
          if (spaceLeft >= toastRect.width + 20) {
            position = 'left';
            left = targetRect.left - toastRect.width - 30 + offset.x;
            top = center.centerY - toastRect.height / 2 + offset.y;
          }
          break;
        case 'right':
          if (spaceRight >= toastRect.width + 20) {
            position = 'right';
            left = targetRect.right + 30 + offset.x;
            top = center.centerY - toastRect.height / 2 + offset.y;
          } else {
          }
          break;
      }
    }

    // If preferredSide couldn't be used or wasn't specified, calculate optimal position
    if (!position) {
      // Check if we have more vertical space or horizontal space
      const verticalSpace = Math.max(spaceAbove, spaceBelow);
      const horizontalSpace = Math.max(spaceLeft, spaceRight);

      if (verticalSpace >= horizontalSpace) {
        // Prefer vertical positioning (top/bottom)
        if (spaceAbove >= spaceBelow) {
          // Position above
          position = 'top';
          left = center.centerX - toastRect.width / 2 + offset.x;
          top = targetRect.top - toastRect.height - 30 + offset.y;
        } else {
          // Position below
          position = 'bottom';
          left = center.centerX - toastRect.width / 2 + offset.x;
          top = targetRect.bottom + 30 + offset.y;
        }
      } else {
        // Prefer horizontal positioning (left/right)
        if (spaceLeft >= spaceRight) {
          // Position to the left
          position = 'left';
          left = targetRect.left - toastRect.width - 30 + offset.x;
          top = center.centerY - toastRect.height / 2 + offset.y;
        } else {
          // Position to the right
          position = 'right';
          left = targetRect.right + 30 + offset.x;
          top = center.centerY - toastRect.height / 2 + offset.y;
        }
      }
    }

    // Ensure toast stays within viewport bounds
    if (left < 10) left = 10;
    if (left + toastRect.width > viewportWidth - 10) {
      left = viewportWidth - toastRect.width - 10;
    }
    if (top < 10) top = 10;
    if (top + toastRect.height > viewportHeight - 10) {
      top = viewportHeight - toastRect.height - 10;
    }

    return { position, left, top, targetCenter: { x: center.centerX, y: center.centerY } };
  }

  // Position the toast using intelligent positioning
  positionToast(targetSelector, position, offset, preferredSide = null, subStep = false) {
    // For sub-steps, don't reposition the toast, just update the arrow
    if (subStep) {
      this.removeCurrentArrow();
      this.createArrow(targetSelector, position, offset);
      return;
    }

    // If position is specified, use it; otherwise calculate optimal position
    let positioning;

    if (position && position !== 'auto') {
      // Use specified position with fallback logic
      positioning = this.calculateSpecifiedPosition(targetSelector, position, offset);
    } else {
      // Calculate optimal position automatically
      positioning = this.calculateOptimalPosition(targetSelector, offset, preferredSide);
    }

    if (!positioning) return;

    this.currentToast.style.left = `${positioning.left}px`;
    this.currentToast.style.top = `${positioning.top}px`;

    // Create arrow pointing to the target
    this.createArrow(targetSelector, positioning.position, offset);
  }

  // Calculate position for specified direction (with fallback)
  calculateSpecifiedPosition(targetSelector, position, offset) {
    const center = this.getElementCenter(targetSelector);
    if (!center) return null;

    const toastRect = this.currentToast.getBoundingClientRect();
    const toastRectCenter = {
      x: toastRect.left + toastRect.width / 2,
      y: toastRect.top + toastRect.height / 2,
    };
    const targetRect = center.rect;
    // the difference in height between the toast and the target
    const toastTargetCenterDelta = toastRect.height - targetRect.height;
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;

    let left, top;

    switch (position) {
      case 'top':
        // Arrow points down: straight vertical line from toast bottom to target center
        startX = center.centerX; // Start at target's X position (horizontal alignment)
        startY = toastRect.bottom; // Start at toast bottom edge
        // subtract  half the distance between the toast and the target
        endX = center.centerX - toastRect.width / 2; // End at target center X
        endY = center.centerY - toastRect.height / 2; // End 10px before target center

        break;
      case 'bottom':
        // Arrow points up: straight vertical line from toast top to target center
        startX = center.centerX; // Start at target's X position (horizontal alignment)
        startY = toastRect.top; // Start at toast top edge
        endX = center.centerX - toastRect.width / 2; // End at target center X
        endY = center.centerY + toastRect.height / 2; // End 10px before target center
        break;
      case 'left':
        // Arrow points right: horizontal line from toast right to target center
        startX = toastRect.right; // Start at toast right edge
        startY = center.centerY; // Start at target's Y position (vertical alignment)
        endX = center.centerX; // End 10px before target center
        endY = center.centerY - toastRect.height / 2; // End at target center Y
        break;
      case 'right':
        // Arrow points left: horizontal line from toast left to target center
        startX = toastRect.left; // Start at toast left edge
        startY = center.centerY; // Start at target's Y position (vertical alignment)
        endX = center.centerX; // End 10px before target center
        endY = center.centerY - toastRect.height / 2; // End at target center Y
        break;
      default:
        return this.calculateOptimalPosition(targetSelector, offset);
    }

    // Ensure toast stays within viewport
    if (left < 10) left = 10;
    if (left + toastRect.width > viewportWidth - 10) {
      left = viewportWidth - toastRect.width - 10;
    }
    if (top < 10) top = 10;
    if (top + toastRect.height > viewportHeight - 10) {
      top = viewportHeight - toastRect.height - 10;
    }

    return { position, left, top, targetCenter: { x: center.centerX, y: center.centerY } };
  }

  // Remove current toast
  removeCurrentToast() {
    // removeCurrentToast called
    if (this.currentToast && this.currentToast.parentNode) {
      // Removing toast from DOM
      this.currentToast.parentNode.removeChild(this.currentToast);
      this.currentToast = null;
    }

    // Also remove any existing arrow
    this.removeCurrentArrow();
  }

  // Create and position an arrow pointing to the target
  createArrow(targetSelector, position, offset) {
    const center = this.getElementCenter(targetSelector);
    const toastColor = 'rgba(11, 255, 255, 0.3)';

    if (!center || !this.currentToast) return;

    const toastRect = this.currentToast.getBoundingClientRect();
    //
    const targetRect = center.rect;
    const userToggle = document.getElementById('users-toggle');
    // find the text-node (should be the emoji)
    const textNode = Array.from(userToggle.childNodes).find((n) => n.nodeType === Node.TEXT_NODE);

    const range = document.createRange();
    range.selectNode(textNode);

    const textRect = range.getBoundingClientRect();
    const textCenter = {
      x: textRect.left + textRect.width / 2,
      y: textRect.top + textRect.height / 2,
    };

    // Remove any existing arrow
    this.removeCurrentArrow();

    // Create SVG container for the arrow
    this.currentArrow = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    this.currentArrow.style.position = 'fixed';
    this.currentArrow.style.left = '0';
    this.currentArrow.style.top = '0';
    this.currentArrow.style.width = '100%';
    this.currentArrow.style.height = '100%';
    this.currentArrow.style.pointerEvents = 'none';

    // Create arrow marker definition
    const defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');
    const marker = document.createElementNS('http://www.w3.org/2000/svg', 'marker');
    marker.setAttribute('id', 'tutorial-arrowhead');
    marker.setAttribute('markerWidth', '100');
    marker.setAttribute('markerHeight', '100');
    marker.setAttribute('refX', '5');
    marker.setAttribute('refY', '5');
    marker.setAttribute('orient', 'auto');

    const polygon = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
    polygon.setAttribute('points', '0 0, 10 3.5, 0 7');
    polygon.setAttribute('fill', toastColor);
    // lower z index

    marker.appendChild(polygon);
    defs.appendChild(marker);
    this.currentArrow.appendChild(defs);
    this.currentArrow.style.zIndex = '1100';

    // Calculate arrow start and end points based on position
    // Arrow starts from the edge of the toast and creates straight lines
    let startX, startY;
    let endX, endY;

    // Calculate the optimal position for the arrow based on toast and target positions
    const toastCenterX = toastRect.left + toastRect.width / 2;
    const toastCenterY = toastRect.top + toastRect.height / 2;
    const targetCenterX = center.centerX;
    const targetCenterY = center.centerY;

    // Arrow positioning - position: position, target: targetSelector
    // Toast center: toastCenterX, toastCenterY
    // Target center: targetCenterX, targetCenterY

    switch (position) {
      case 'top':
        // Toast is ABOVE target, so arrow points DOWN from toast bottom to target top
        startX = toastCenterX;
        startY = toastRect.bottom + 10;
        endX = targetCenterX;
        endY = targetRect.top - 10;
        break;
      case 'bottom':
        // Toast is BELOW target, so arrow points UP from toast top to target bottom
        startX = toastCenterX;
        startY = toastRect.top - 10;
        endX = targetCenterX;
        endY = targetRect.bottom + 10;
        break;
      case 'left':
        // Toast is to the LEFT of target, so arrow points RIGHT from toast right to target left
        startX = toastRect.right + 10;
        startY = toastCenterY;
        endX = targetRect.left - 10;
        endY = targetCenterY;
        break;
      case 'right':
        // Toast is to the RIGHT of target, so arrow points LEFT from toast left to target right
        startX = toastRect.left - 10;
        startY = toastCenterY;
        endX = targetRect.right + 10;
        endY = targetCenterY;
        break;
      default:
        // Auto-calculate based on relative positions
        const deltaX = targetCenterX - toastCenterX;
        const deltaY = targetCenterY - toastCenterY;

        if (Math.abs(deltaX) > Math.abs(deltaY)) {
          // Horizontal arrow
          if (deltaX > 0) {
            // Target is to the right
            startX = toastRect.right + 10;
            startY = toastCenterY;
            endX = targetRect.left - 10;
            endY = targetCenterY;
          } else {
            // Target is to the left
            startX = toastRect.left - 10;
            startY = toastCenterY;
            endX = targetRect.right + 10;
            endY = targetCenterY;
          }
        } else {
          // Vertical arrow
          if (deltaY > 0) {
            // Target is below
            startX = toastCenterX;
            startY = toastRect.bottom + 10;
            endX = targetCenterX;
            endY = targetRect.top - 10;
          } else {
            // Target is above
            startX = toastCenterX;
            startY = toastRect.top - 10;
            endX = targetCenterX;
            endY = targetRect.bottom + 10;
          }
        }
        break;
    }

    // Create just the arrowhead (no line)
    const arrowhead = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
    const arrowheadSize = 15; // Smaller arrowhead for better appearance
    let points;

    // Use fixed arrow direction based on position parameter
    if (position === 'top') {
      // Toast is above target, arrow points down
      points = `
        ${endX},${endY}
        ${endX - arrowheadSize},${endY - arrowheadSize}
        ${endX + arrowheadSize},${endY - arrowheadSize}
      `;
    } else if (position === 'bottom') {
      // Toast is below target, arrow points up
      points = `
        ${endX},${endY}
        ${endX - arrowheadSize},${endY + arrowheadSize}
        ${endX + arrowheadSize},${endY + arrowheadSize}
      `;
    } else if (position === 'left') {
      // Toast is to the left of target, arrow points right
      points = `
        ${endX},${endY}
        ${endX - arrowheadSize},${endY - arrowheadSize}
        ${endX - arrowheadSize},${endY + arrowheadSize}
      `;
    } else if (position === 'right') {
      // Toast is to the right of target, arrow points left
      points = `
        ${endX},${endY}
        ${endX + arrowheadSize},${endY - arrowheadSize}
        ${endX + arrowheadSize},${endY + arrowheadSize}
      `;
    } else {
      // Auto-calculate based on relative positions (fallback)
      const deltaX = endX - startX;
      const deltaY = endY - startY;

      if (Math.abs(deltaX) > Math.abs(deltaY)) {
        // Horizontal arrow
        if (deltaX > 0) {
          // Arrow points right
          points = `
            ${endX},${endY}
            ${endX - arrowheadSize},${endY - arrowheadSize}
            ${endX - arrowheadSize},${endY + arrowheadSize}
          `;
        } else {
          // Arrow points left
          points = `
            ${endX},${endY}
            ${endX + arrowheadSize},${endY - arrowheadSize}
            ${endX + arrowheadSize},${endY + arrowheadSize}
          `;
        }
      } else {
        // Vertical arrow
        if (deltaY > 0) {
          // Arrow points down
          points = `
            ${endX},${endY}
            ${endX - arrowheadSize},${endY - arrowheadSize}
            ${endX + arrowheadSize},${endY - arrowheadSize}
          `;
        } else {
          // Arrow points up
          points = `
            ${endX},${endY}
            ${endX - arrowheadSize},${endY + arrowheadSize}
            ${endX + arrowheadSize},${endY + arrowheadSize}
          `;
        }
      }
    }

    arrowhead.setAttribute('points', points);

    arrowhead.setAttribute('fill', toastColor);
    arrowhead.classList.add('tutorial-arrow');

    this.currentArrow.appendChild(arrowhead);
    document.body.appendChild(this.currentArrow);
  }

  // Remove current arrow
  removeCurrentArrow() {
    if (this.currentArrow && this.currentArrow.parentNode) {
      this.currentArrow.parentNode.removeChild(this.currentArrow);
      this.currentArrow = null;
    }
  }

  // Update arrow target without changing orientation (for sub-steps)
  updateArrowTarget(targetSelector, offset) {
    if (!this.currentArrow || !this.currentToast) return;

    // Just recreate the arrow with the same position but new target
    // This is simpler and more reliable
    this.removeCurrentArrow();

    // Use the same position as the first sub-step to maintain consistency
    const effectivePosition = 'bottom'; // Hardcode for now since we know it's bottom
    this.createArrow(targetSelector, effectivePosition, offset);
  }
}

// Simple tutorial sequence function
function startTutorialSequence() {
  const tutorial = new TutorialPositioner();

  const tutorialSteps = [
    {
      message: 'Click here to see online users and start private chats',
      target: '#users-toggle',
      options: {
        position: null, // Let the system decide the best position
        preferredSide: 'right', // 'top', 'bottom', 'left', 'right', or null for auto
        offset: { x: 0, y: 0 },
        duration: 1600,
        type: 'info',
        fontSize: '16px',
      },
    },
    {
      message: "💡 Click here for quick questions about Ryan's experience",
      target: '#info-toggle',
      options: {
        position: null, // Let the system decide the best position
        preferredSide: 'left', // 'top', 'bottom', 'left', 'right', or null for auto
        offset: { x: 0, y: 0 },
        duration: 1600,
        type: 'info',
        fontSize: '16px',
      },
    },
    {
      message: 'Toggle this to chat with the AI assistant about projects',
      target: '.bot-robot-button',
      options: {
        position: null, // Let the system decide the best position
        preferredSide: 'top', // 'top', 'bottom', 'left', 'right', or null for auto
        offset: { x: 0, y: 0 },
        duration: 1600,
        type: 'info',
        fontSize: '16px',
      },
    },

    [
      {
        message: 'Audio Controls - Click to enable/disable audio responses',
        target: '#audio-toggle',
        options: {
          position: null, // Let the system decide the best position
          preferredSide: 'bottom', // 'top', 'bottom', 'left', 'right', or null for auto
          offset: { x: 0, y: 0 },
          duration: 1600,
          type: 'info',
          fontSize: '16px',
        },
      },
      {
        message: 'Audio Controls - scroll for audio speed',
        target: '#speed-toggle',
        options: {
          position: null, // Let the system decide the best position
          preferredSide: 'bottom', // 'top', 'bottom', 'left', 'right', or null for auto
          offset: { x: 0, y: 0 },
          duration: 1600,
          type: 'info',
          fontSize: '16px',
        },
      },
      {
        message: 'Audio Controls - Click for info',
        target: '#help-button',
        options: {
          position: null, // Let the system decide the best position
          preferredSide: 'bottom', // 'top', 'bottom', 'left', 'right', or null for auto
          offset: { x: 0, y: 0 },
          duration: 1600,
          type: 'info',
          fontSize: '16px',
        },
      },
    ],

    {
      message: 'Set custom username if desired',
      target: '.username-display',
      options: {
        position: null, // Let the system decide the best position
        preferredSide: 'bottom', // 'top', 'bottom', 'left', 'right', or null for auto
        offset: { x: 0, y: 0 },
        duration: 1600,
        type: 'info',
        fontSize: '16px',
      },
    },
    [
      {
        message: 'Settings Controls - Background settings and logout',
        target: '#logout-btn',
        options: {
          position: null, // Let the system decide the best position
          preferredSide: 'bottom', // 'top', 'bottom', 'left', 'right', or null for auto
          offset: { x: 0, y: 0 },
          duration: 1600,
          type: 'info',
          fontSize: '16px',
        },
      },
      {
        message: 'Settings Controls - Background settings',
        target: '#settings-btn',
        options: {
          position: null, // Let the system decide the best position
          preferredSide: 'bottom', // 'top', 'bottom', 'left', 'right', or null for auto
          offset: { x: 0, y: 0 },
          duration: 1600,
          type: 'info',
          fontSize: '16px',
        },
      },
      {
        message: 'Settings Controls - Cache Info',
        target: '#cache-btn',
        options: {
          position: null, // Let the system decide the best position
          preferredSide: 'bottom', // 'top', 'bottom', 'left', 'right', or null for auto
          offset: { x: 0, y: 0 },
          duration: 1600,
          type: 'info',
          fontSize: '16px',
        },
      },
    ],
  ];

  let currentStep = 0;

  function showNextStep() {
    if (currentStep >= tutorialSteps.length) {
      return;
    }

    const step = tutorialSteps[currentStep];

    if (Array.isArray(step)) {
      // Handle array of steps - show them sequentially
      let subStepIndex = 0;

      const showSubStep = () => {
        if (subStepIndex < step.length) {
          const subStep = step[subStepIndex];
          // Showing sub-step
          // First sub-step creates the toast, subsequent ones update it
          const isSubStep = subStepIndex > 0;
          const isInArray = true; // All items in an array should not set auto-remove timers
          // Calling showTutorialToast with subStep
          // Pass the first sub-step's position for consistency
          const firstSubStepPosition = step[0].options.position;
          tutorial.showTutorialToast(
            subStep.message,
            subStep.target,
            subStep.options,
            isSubStep,
            isInArray,
            firstSubStepPosition
          );
          subStepIndex++;

          // Schedule next sub-step or move to next main step
          if (subStepIndex < step.length) {
            setTimeout(showSubStep, subStep.options.duration + 100);
          } else {
            // All sub-steps done, set timer to remove toast and move to next main step
            setTimeout(() => {
              tutorial.removeCurrentToast();
              currentStep++;
              setTimeout(showNextStep, 100);
            }, subStep.options.duration + 100);
          }
        }
      };

      showSubStep();
    } else {
      // Handle single step
      tutorial.showTutorialToast(step.message, step.target, step.options);
      currentStep++;
      setTimeout(showNextStep, step.options.duration + 100);
    }
  }

  // Start the sequence
  showNextStep();
}

// ===================================
// RESPONSE CACHING SYSTEM
// ===================================

// Cache system removed - no more local storage caching

// Sync with backend cache after initialization

// ===================================
// CACHED MESSAGE DISPLAY
// ===================================

// Add a bot message with cache indicator
// Cache system removed - no more local storage caching

// Global flag to track if we're generating a "new response" (shouldn't be cached)
let isGeneratingNewResponse = false;

// Global variable to store TTS data for the current response
let currentResponseTTS = null;

// Simple toast notification function
async function showCacheManager() {
  try {
    // Fetch cache stats from the public endpoint
    const response = await fetch('/cache/public/entries');
    const data = await response.json();

    if (data.success) {
      const entries = data.data.entries || [];
      const totalEntries = entries.length;
      const totalHits = entries.reduce((sum, entry) => sum + (entry.hit_count || 0), 0);
      const avgHits = totalEntries > 0 ? (totalHits / totalEntries).toFixed(1) : 0;

      // Create a simple stats popup
      const statsHtml = `
        <div style="padding: 20px; max-width: 400px;">
          <h3>📊 Cache Statistics</h3>
          <div style="margin: 15px 0;">
            <strong>Total Cached Responses:</strong> ${totalEntries}<br>
            <strong>Total Cache Hits:</strong> ${totalHits}<br>
            <strong>Average Hits per Response:</strong> ${avgHits}<br>
            <strong>Most Popular:</strong> ${
              entries.length > 0 ? entries[0].question.substring(0, 50) + '...' : 'None'
            }
          </div>
          <div style="margin-top: 20px; font-size: 12px; color: #666;">
            💡 Cache helps reduce response time for repeated questions
          </div>
        </div>
      `;

      // Show as a toast or alert
      showToast(statsHtml, 'info', 5000);
    } else {
      showToast('Failed to load cache statistics', 'error');
    }
  } catch (error) {
    console.error('Error loading cache stats:', error);
    showToast('Error loading cache statistics', 'error');
  }
}

function showToast(message, type = 'info', duration = 3000) {
  // Create toast container if it doesn't exist
  let toastContainer = document.getElementById('toast-container');
  if (!toastContainer) {
    toastContainer = document.createElement('div');
    toastContainer.id = 'toast-container';
    document.body.appendChild(toastContainer);
  }

  // Create toast element
  const toast = document.createElement('div');
  toast.className = `toast ${type} slide-animation`;
  toast.innerHTML = `<div class="toast-text">${message}</div>`;

  // Add to container
  toastContainer.appendChild(toast);

  // Animate in
  setTimeout(() => {
    toast.classList.add('show');
  }, 10);

  // Auto remove after duration
  setTimeout(() => {
    toast.classList.add('hide');
    setTimeout(() => {
      if (toast.parentNode) {
        toast.parentNode.removeChild(toast);
      }
    }, 300);
  }, duration);
}

// Regenerate a response by sending the question again (without affecting cache)
// Cache system removed - no more local storage caching

// Add generated timestamp to a response (fresh or cached)
async function addGeneratedTimestamp(
  messageElement,
  voiceB64 = null,
  isCached = false,
  cachedModel = null
) {
  // Create timestamp indicator
  const timestampIndicator = document.createElement('div');
  timestampIndicator.className = isCached ? 'cached-timestamp' : 'generated-timestamp';

  const now = new Date();
  const timestamp = now.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: true,
  });

  // Get the model information
  let model = 'unknown';
  if (isCached && cachedModel) {
    // Use the cached model if available
    model = cachedModel;
  } else {
    // Get the current model from the server for fresh responses
    try {
      const response = await fetch('/cache/model-info');
      const data = await response.json();
      if (data.success && data.data?.model) {
        model = data.data.model;
      }
    } catch (error) {
      // Could not fetch model info
    }
  }

  // Create timestamp content
  if (isCached) {
    timestampIndicator.innerHTML = `<span class="timestamp-text">💾 Cached response from ${model}</span>`;
  } else {
    timestampIndicator.innerHTML = `<span class="timestamp-text">🕐 Generated ${timestamp} by ${model}</span>`;
  }

  // Insert the timestamp at the beginning of the message
  messageElement.insertBefore(timestampIndicator, messageElement.firstChild);

  // Add regenerate button for cached responses
  if (isCached) {
    const regenerateButton = document.createElement('button');
    regenerateButton.className = 'regenerate-btn';
    regenerateButton.innerHTML = '🔄 Regenerate';
    regenerateButton.title = 'Generate a fresh response';
    regenerateButton.onclick = () => {
      // Find the user's question from recent messages
      const messages = document.querySelectorAll('.message');
      const userMessages = Array.from(messages)
        .filter((msg) => msg.classList.contains('user'))
        .slice(-10); // Look at last 10 user messages to find the original question

      if (userMessages.length > 0) {
        // Find the most recent message that doesn't contain [REGENERATE] or double @bot
        let originalQuestion = null;
        for (let i = userMessages.length - 1; i >= 0; i--) {
          const messageText = userMessages[i].querySelector('.message-text');
          if (messageText) {
            const content = messageText.textContent.trim();
            // Skip messages that are regenerate attempts or have double @bot
            if (!content.includes('[REGENERATE]') && !content.includes('@bot @bot')) {
              originalQuestion = content;
              break;
            }
          }
        }

        if (originalQuestion) {
          // Remove @bot prefix if it exists to get the clean question
          let question = originalQuestion.replace(/@bot\s*/i, '').trim();

          // Send the question again with a regenerate flag to force cache bypass
          if (socket && socket.readyState === WebSocket.OPEN) {
            socket.send(
              JSON.stringify({
                type: 'chat_message',
                data: {
                  message: '@bot [REGENERATE] ' + question,
                  displayName: window.displayName || currentUsername,
                },
              })
            );
          }
        }
      }
    };

    // Add the regenerate button to the timestamp container
    timestampIndicator.appendChild(regenerateButton);
  }

  // Add TTS replay button at the end of the message if voice data is available
  if (voiceB64) {
    const replayButton = document.createElement('button');
    replayButton.className = 'tts-replay-btn-small';
    replayButton.innerHTML = '🔊';
    replayButton.title = 'Replay TTS audio';
    replayButton.onclick = () => replayTTS(voiceB64);

    // Append the button to the end of the message
    messageElement.appendChild(replayButton);
  }
}

// Cache system removed - no more local storage caching

// Function to replay TTS audio
function replayTTS(voiceB64) {
  try {
    // Mark user interaction
    if (!userHasInteracted) {
      userHasInteracted = true;
    }

    // Create audio element from base64 data
    const audio = new Audio('data:audio/wav;base64,' + voiceB64);

    // Set audio properties
    audio.volume = audioVolume;
    audio.playbackRate = audioPlaybackRate;

    // Play the audio
    audio
      .play()
      .then(() => {
        // TTS replay successful
      })
      .catch((error) => {
        console.error('🔇 TTS replay failed:', error);
        showToast('Failed to replay audio', 'error', 2000);
      });
  } catch (error) {
    console.error('🔇 TTS replay error:', error);
    showToast('Failed to replay audio', 'error', 2000);
  }
}

// Sync frontend cache with backend cache
// Cache system removed - no more local storage caching

// Add tutorial styles to document
const tutorialStyles = `
.tutorial-toast {
  background: rgba(52, 152, 219, 0.95);
  color: white;
  padding: 15px 20px;
  border-radius: 8px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.5);
  font-size: 14px;
  line-height: 1.4;
  position: fixed;
  z-index: 99999;
  max-width: 300px;
  backdrop-filter: blur(10px);
  border: 2px solid rgba(255, 255, 255, 0.3);
  animation: tutorialFadeIn 0.3s ease-out;
  font-weight: 500;
}

@keyframes tutorialFadeIn {
  from {
    opacity: 0;
    transform: translateY(-10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes arrowDraw {
  from {
    stroke-dashoffset: 100;
  }
  to {
    stroke-dashoffset: 0;
  }
}

.tutorial-arrow {
  animation: arrowDraw 0.5s ease-out 0.2s both;
}

.tutorial-content {
  margin-bottom: 10px;
}

.tutorial-toast.info {
  border-left: 4px solid #3498db;
}

.tutorial-toast.success {
  border-left: 4px solid #2ecc71;
}

.tutorial-toast.warning {
  border-left: 4px solid #f39c12;
}

.tutorial-toast.error {
  border-left: 4px solid #e74c3c;
}
`;

// Add styles to document when script loads
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => {
    const styleSheet = document.createElement('style');
    styleSheet.textContent = tutorialStyles;
    document.head.appendChild(styleSheet);
  });
} else {
  const styleSheet = document.createElement('style');
  styleSheet.textContent = tutorialStyles;
  document.head.appendChild(styleSheet);
}

// Cleanup function for page unload
function cleanup() {
  clearTimers();
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.close(1000, 'Page unload');
  }
}

// Cleanup on page unload
window.addEventListener('beforeunload', cleanup);
window.addEventListener('unload', cleanup);
