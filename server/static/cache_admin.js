// Configuration
const API_BASE = '';

// Global variables
let allCacheEntries = [];
let clientCacheEntries = []; // Separate array for client cache entries
let currentView = 'admin';
let currentEditingQuestion = null;

// Utility functions
function formatBytes(bytes) {
  if (bytes === 0) return '0 Bytes';
  const k = 1024;
  const sizes = ['Bytes', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

// Base64 encoding for Basic Auth
function encodeBase64(str) {
  return window.btoa(unescape(encodeURIComponent(str)));
}

// Get admin credentials from sessionStorage (set by login form)
function getAdminCredentials() {
  const username = sessionStorage.getItem('cache_admin_username');
  const password = sessionStorage.getItem('cache_admin_password');

  // Checking credentials

  if (!username || !password) {
    // No credentials found, redirecting to login
    // Redirect to login if no credentials
    window.location.href = '/cache/login';
    return null;
  }

  // Credentials found
  return { username, password };
}

// Check if we're authenticated by checking credentials exist
function checkAuthentication() {
  const creds = getAdminCredentials();
  if (!creds) {
    // No credentials found, redirecting to login
    window.location.href = '/cache/login';
    return false;
  }

  // Credentials found, proceeding with authenticated requests
  return true;
}

// Get authentication headers
function getAuthHeaders() {
  const creds = getAdminCredentials();
  if (!creds) {
    throw new Error('No credentials available');
  }

  const authString = `${creds.username}:${creds.password}`;
  const encodedAuth = encodeBase64(authString);

  return {
    'Content-Type': 'application/json',
    Authorization: `Basic ${encodedAuth}`,
  };
}

// Handle authentication errors
function handleAuthError(error) {
  if (error.message.includes('401') || error.message.includes('Unauthorized')) {
    // Authentication failed, redirecting to login
    sessionStorage.removeItem('cache_admin_username');
    sessionStorage.removeItem('cache_admin_password');
    window.location.href = '/cache/login';
    return true;
  }
  return false;
}

// Show status message
function showStatus(message, type = 'info') {
  const statusDiv = document.getElementById('status');
  if (statusDiv) {
    statusDiv.textContent = message;
    statusDiv.className = `status ${type}`;
    statusDiv.style.display = 'block';

    // Auto-hide after 5 seconds
    setTimeout(() => {
      statusDiv.style.display = 'none';
    }, 5000);
  }
}

// Load cache status
async function loadCacheStatus() {
  // Loading cache status
  try {
    const response = await fetch(`${API_BASE}/cache/status`, {
      headers: getAuthHeaders(),
    });

    // Cache status response
    const data = await response.json();
    // Cache status data

    if (data.success) {
      document.getElementById('total-entries').textContent = data.data.total_entries;
      document.getElementById('cache-size').textContent = formatBytes(data.data.cache_file_size);
      document.getElementById('cache-status').textContent = data.data.cache_file_exists
        ? 'Active'
        : 'No Cache';

      // Display cache breakdown
      const serverEntries = data.data.server_entries || 0;
      const clientEntries = data.data.client_entries || 0;
      const breakdownText = `Server: ${serverEntries}, Client: ${clientEntries}`;

      // Update or create breakdown element
      let breakdownElement = document.getElementById('cache-breakdown');
      const statsContainer = document.querySelector('.stats');

      if (!breakdownElement && statsContainer) {
        breakdownElement = document.createElement('div');
        breakdownElement.id = 'cache-breakdown';
        breakdownElement.className = 'stat-card';
        statsContainer.appendChild(breakdownElement);
      }

      if (breakdownElement) {
        breakdownElement.innerHTML = `
          <h3>Cache Breakdown</h3>
          <div class="value">${breakdownText}</div>
        `;
      }

      // Also update the tab counts if they exist
      if (document.getElementById('count-server')) {
        document.getElementById('count-server').textContent = serverEntries;
        document.getElementById('count-client').textContent = clientEntries;
        document.getElementById('count-all').textContent = data.data.total_entries || 0;
      }

      // Display model distribution
      const modelDist = data.data.model_distribution || {};
      if (Object.keys(modelDist).length > 0) {
        const distText = Object.entries(modelDist)
          .map(([model, count]) => `${model}: ${count}`)
          .join(', ');
        document.getElementById('model-distribution').textContent = distText;
      } else {
        document.getElementById('model-distribution').textContent = 'No data';
      }
    } else {
      // Cache status failed
      showStatus(data.message, 'error');
    }
  } catch (error) {
    // Cache status error
    if (!handleAuthError(error)) {
      showStatus(`Error loading cache status: ${error.message}`, 'error');
    }
  }

  // Load current model info
  try {
    const modelResponse = await fetch(`${API_BASE}/cache/model-info`);
    const modelData = await modelResponse.json();

    if (modelData.success) {
      document.getElementById('current-model').textContent = modelData.data.model;
    } else {
      document.getElementById('current-model').textContent = 'Unknown';
    }
  } catch (error) {
    // Could not fetch model info
    document.getElementById('current-model').textContent = 'Unknown';
  }
}

// Toggle cache entry expand/collapse
function toggleCacheEntry(index) {
  const entriesContainer = document.getElementById('cache-entries');
  const entries = entriesContainer.querySelectorAll('.cache-entry');
  const entry = entries[index];
  const toggleBtn = entry.querySelector('.cache-entry-toggle');

  if (entry.classList.contains('collapsed')) {
    entry.classList.remove('collapsed');
    toggleBtn.textContent = '🔽 Collapse';
  } else {
    entry.classList.add('collapsed');
    toggleBtn.textContent = '▶️ Expand';
  }
}

// Expand all cache entries
function expandAllEntries() {
  const entriesContainer = document.getElementById('cache-entries');
  const entries = entriesContainer.querySelectorAll('.cache-entry');
  entries.forEach((entry, index) => {
    if (entry.classList.contains('collapsed')) {
      toggleCacheEntry(index);
    }
  });
}

// Collapse all cache entries
function collapseAllEntries() {
  const entriesContainer = document.getElementById('cache-entries');
  const entries = entriesContainer.querySelectorAll('.cache-entry');
  entries.forEach((entry, index) => {
    if (!entry.classList.contains('collapsed')) {
      toggleCacheEntry(index);
    }
  });
}

// Filter cache entries by search term
function filterEntries() {
  const searchTerm = document.getElementById('entry-search').value.toLowerCase();
  const entriesContainer = document.getElementById('cache-entries');
  const entries = entriesContainer.querySelectorAll('.cache-entry');

  entries.forEach((entry) => {
    const question = entry.querySelector('.cache-entry-title').textContent.toLowerCase();
    if (question.includes(searchTerm)) {
      entry.classList.remove('hidden');
    } else {
      entry.classList.add('hidden');
    }
  });
}

// Clear search and show all entries
function clearSearch() {
  document.getElementById('entry-search').value = '';
  const entries = document.querySelectorAll('.cache-entry');
  entries.forEach((entry) => {
    entry.classList.remove('hidden');
  });
}

// Load cache entries

async function loadCacheEntries() {
  // Loading cache entries
  const loading = document.getElementById('entries-loading');

  loading.classList.add('show');

  try {
    const response = await fetch(`${API_BASE}/cache/entries`, {
      headers: getAuthHeaders(),
    });

    // Cache entries response
    const data = await response.json();

    if (data.success) {
      // Only load server/admin cache entries, filter out client entries
      allCacheEntries = (data.data.entries || []).filter((entry) => entry.source === 'server');
      // Loaded server entries

      // Update tab counts
      updateTabCounts();

      // Render entries for current tab
      renderCacheEntries();
    } else {
      showStatus(data.message, 'error');
    }
  } catch (error) {
    showStatus(`Error loading cache entries: ${error.message}`, 'error');
  } finally {
    loading.classList.remove('show');
  }
}

// Try to get client cache entries from main chat page
async function loadClientCacheEntriesFromMainChat() {
  try {
    // Check if main chat page is open in another tab
    if (window.opener && window.opener.ResponseCache) {
      // Main chat page detected, loading client cache entries

      const clientEntries = window.opener.ResponseCache.getTopResponses(50);

      // Store client entries in separate array
      clientCacheEntries = clientEntries.map((entry) => ({
        question: entry.question,
        response: entry.response,
        timestamp: entry.timestamp,
        hit_count: entry.hitCount,
        model: entry.model || 'unknown',
        source: 'client',
      }));

      // Loaded client cache entries from main chat page
    } else {
      // Main chat page not detected - client cache entries not available
      clientCacheEntries = [];
    }
  } catch (error) {
    // Error loading client cache entries from main chat
    clientCacheEntries = [];
  }
}

// Refresh client cache entries manually
async function refreshClientCache() {
  try {
    showStatus('Refreshing client cache entries...', 'info');

    // Try to load client entries from main chat page
    await loadClientCacheEntriesFromMainChat();

    // Update tab counts and re-render
    updateTabCounts();
    renderCacheEntries();

    if (clientCacheEntries.length > 0) {
      showStatus(
        `✅ Refreshed client cache: ${clientCacheEntries.length} entries loaded`,
        'success'
      );
    } else {
      showStatus('ℹ️ No client cache entries found. Make sure the main chat page is open.', 'info');
    }
  } catch (error) {
    showStatus(`Error refreshing client cache: ${error.message}`, 'error');
  }
}

function updateTabCounts() {
  // Cache entries count
}

function renderCacheEntries() {
  const entriesContainer = document.getElementById('cache-entries');

  if (!entriesContainer) return;

  entriesContainer.innerHTML = '';

  // Only show server/admin cache entries in the main dashboard
  const entriesToShow = allCacheEntries;

  if (entriesToShow.length === 0) {
    entriesContainer.innerHTML =
      '<p style="text-align: center; color: rgba(255,255,255,0.6);">No cache entries found</p>';
    return;
  }

  entriesToShow.forEach((entry, index) => {
    const entryDiv = document.createElement('div');
    entryDiv.className = 'cache-entry collapsed';
    entryDiv.innerHTML = `
      <div class="cache-entry-header" onclick="toggleCacheEntry(${index})">
        <h3 class="cache-entry-title">${entry.question}</h3>
        <div class="cache-entry-meta">
          <button class="cache-entry-toggle" onclick="event.stopPropagation(); toggleCacheEntry(${index})">
            ▶️ Expand
          </button>
        </div>
      </div>
      <div class="cache-entry-details">
        <p><strong>Response Length:</strong> ${entry.response.length} characters</p>
        <p><strong>Hit Count:</strong> ${entry.hit_count}</p>
        <div class="model-info">
          <strong>🤖 Model:</strong> ${entry.model || 'unknown'}
        </div>
        <p><strong>Created:</strong> ${new Date(entry.timestamp).toLocaleString()}</p>
        <div class="actions">
          <button onclick="viewResponse('${entry.question.replace(/'/g, "\\'")}', '${entry.response
      .replace(/'/g, "\\'")
      .replace(/\n/g, '\\n')}')" class="info">👁️ View Response</button>
          <button onclick="editResponse('${entry.question.replace(/'/g, "\\'")}', '${entry.response
      .replace(/'/g, "\\'")
      .replace(/\n/g, '\\n')}')" class="secondary">✏️ Edit Response</button>
          <button onclick="toggleTTS('${entry.question.replace(
            /'/g,
            "\\'"
          )}')" class="primary" id="tts-btn-${entry.question.replace(
      /[^a-zA-Z0-9]/g,
      '_'
    )}">🔊 Listen TTS</button>
          <button onclick="regenerateEntry('${entry.question.replace(
            /'/g,
            "\\'"
          )}')" class="warning">🔄 Regenerate</button>
          <button onclick="regenerateTTS('${entry.question.replace(
            /'/g,
            "\\'"
          )}')" class="success">🎤 Regenerate TTS</button>
          <button onclick="removeEntry('${entry.question.replace(
            /'/g,
            "\\'"
          )}')" class="danger">🗑️ Remove</button>
        </div>
      </div>
    `;
    entriesContainer.appendChild(entryDiv);
  });
}

function renderClientCacheEntries() {
  const entriesContainer = document.getElementById('cache-entries');

  if (!entriesContainer) return;

  entriesContainer.innerHTML = '';

  // Show client cache entries
  const entriesToShow = clientCacheEntries;

  if (entriesToShow.length === 0) {
    entriesContainer.innerHTML =
      '<p style="text-align: center; color: rgba(255,255,255,0.6);">No cache entries found</p>';
    return;
  }

  entriesToShow.forEach((entry, index) => {
    const entryDiv = document.createElement('div');
    entryDiv.className = 'cache-entry collapsed';
    entryDiv.innerHTML = `
      <div class="cache-entry-header" onclick="toggleCacheEntry(${index})">
        <h3 class="cache-entry-title">${entry.question}</h3>
        <div class="cache-entry-meta">
          <button class="cache-entry-toggle" onclick="event.stopPropagation(); toggleCacheEntry(${index})">
            ▶️ Expand
          </button>
        </div>
      </div>
      <div class="cache-entry-details">
        <p><strong>Response Length:</strong> ${entry.response.length} characters</p>
        <p><strong>Hit Count:</strong> ${entry.hit_count}</p>
        <div class="model-info">
          <strong>🤖 Model:</strong> ${entry.model || 'unknown'}
        </div>
        <p><strong>Created:</strong> ${new Date(entry.timestamp).toLocaleString()}</p>
        <div class="actions">
          <button onclick="viewResponse('${entry.question.replace(/'/g, "\\'")}', '${entry.response
      .replace(/'/g, "\\'")
      .replace(/\n/g, '\\n')}')" class="info">👁️ View Response</button>
          <button onclick="editResponse('${entry.question.replace(/'/g, "\\'")}', '${entry.response
      .replace(/'/g, "\\'")
      .replace(/\n/g, '\\n')}')" class="secondary">✏️ Edit Response</button>
          <button onclick="toggleTTS('${entry.question.replace(
            /'/g,
            "\\'"
          )}')" class="primary" id="tts-btn-${entry.question.replace(
      /[^a-zA-Z0-9]/g,
      '_'
    )}">🔊 Listen TTS</button>
          <button onclick="regenerateEntry('${entry.question.replace(
            /'/g,
            "\\'"
          )}')" class="warning">🔄 Regenerate</button>
          <button onclick="regenerateTTS('${entry.question.replace(
            /'/g,
            "\\'"
          )}')" class="success">🎤 Regenerate TTS</button>
          <button onclick="removeEntry('${entry.question.replace(
            /'/g,
            "\\'"
          )}')" class="danger">🗑️ Remove</button>
        </div>
      </div>
    `;
    entriesContainer.appendChild(entryDiv);
  });
}

// Function to switch between admin and client views
function switchView(view) {
  // Switching view

  // Update navigation buttons
  document.querySelectorAll('.nav-btn').forEach((btn) => {
    btn.classList.remove('active');
  });

  const navButton = document.getElementById(`nav-${view}`);
  if (navButton) {
    navButton.classList.add('active');
  }

  // Update current view
  currentView = view;

  // Show/hide sections based on view
  const adminSections = [
    '.section:nth-child(2)', // Cache Status
    '.section:nth-child(3)', // Cache Statistics
    '.section:nth-child(4)', // Add Cache Entry
    '.section:nth-child(5)', // Bulk Operations
    '.section:nth-child(6)', // Cache Entries
  ];

  if (view === 'admin') {
    // Show admin sections
    adminSections.forEach((selector) => {
      const section = document.querySelector(selector);
      if (section) section.style.display = 'block';
    });

    // Update header for admin view
    const header = document.querySelector('.nav-header h1');
    if (header) {
      header.textContent = '🤖 Cache Admin Dashboard';
    }

    // Load full admin data
    loadCacheStatus();
    loadCacheEntries();
  } else {
    // Hide admin sections
    adminSections.forEach((selector) => {
      const section = document.querySelector(selector);
      if (section) section.style.display = 'none';
    });

    // Update header for client view
    const header = document.querySelector('.nav-header h1');
    if (header) {
      header.textContent = '💻 Client Cache Entries';
    }

    // Load client cache entries
    loadClientCacheEntriesFromMainChat();
    renderClientCacheEntries();
  }
}

// Add cache entry
async function addCacheEntry() {
  const question = document.getElementById('question').value.trim();
  const responseText = document.getElementById('response').value.trim();

  if (!question) {
    showStatus('Please enter a question', 'error');
    return;
  }

  try {
    const response = await fetch(`${API_BASE}/cache/add`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({
        question: question,
        response: responseText || null,
      }),
    });

    const data = await response.json();

    if (data.success) {
      showStatus(data.message, 'success');
      document.getElementById('question').value = '';
      document.getElementById('response').value = '';
      loadCacheStatus();
      loadCacheEntries();
    } else {
      showStatus(data.message, 'error');
    }
  } catch (error) {
    showStatus(`Error adding cache entry: ${error.message}`, 'error');
  }
}

// Remove cache entry
async function removeEntry(question) {
  if (!confirm(`Are you sure you want to remove the cache entry for: "${question}"?`)) {
    return;
  }

  try {
    const response = await fetch(`${API_BASE}/cache/remove`, {
      method: 'DELETE',
      headers: getAuthHeaders(),
      body: JSON.stringify({ question: question }),
    });

    const data = await response.json();

    if (data.success) {
      // Check if this was a client entry
      if (data.data && data.data.source === 'client') {
        showStatus('Client cache entry found. Please remove it from the main chat page.', 'info');

        // Remove from client cache if main chat page is open
        if (window.opener && window.opener.ResponseCache) {
          window.opener.ResponseCache.removeCachedResponse(question);
          showStatus('Client cache entry removed from main chat page.', 'success');
        }
      } else {
        showStatus(data.message, 'success');
      }

      loadCacheStatus();
      loadCacheEntries();
    } else {
      showStatus(data.message, 'error');
    }
  } catch (error) {
    showStatus(`Error removing cache entry: ${error.message}`, 'error');
  }
}

// View response in modal
function viewResponse(question, response) {
  document.getElementById('modal-question').textContent = question;
  document.getElementById('modal-response').textContent = response;
  document.getElementById('response-modal').style.display = 'block';
}

// Close response modal
function closeResponseModal() {
  document.getElementById('response-modal').style.display = 'none';
}

// Edit response
function editResponse(question, response) {
  // Edit response called
  document.getElementById('edit-modal-question').textContent = question;
  document.getElementById('edit-response-text').value = response;
  currentEditingQuestion = question;
  document.getElementById('edit-modal').style.display = 'block';
}

// Close edit modal
function closeEditModal() {
  document.getElementById('edit-modal').style.display = 'none';
  currentEditingQuestion = null;
}

// Save edited response
async function saveEditedResponse() {
  if (!currentEditingQuestion) {
    showStatus('No question selected for editing', 'error');
    return;
  }

  const newResponse = document.getElementById('edit-response-text').value.trim();

  if (!newResponse) {
    showStatus('Response text cannot be empty', 'error');
    return;
  }

  try {
    showStatus('Saving changes...', 'info');

    const response = await fetch(`${API_BASE}/cache/update`, {
      method: 'PUT',
      headers: getAuthHeaders(),
      body: JSON.stringify({
        question: currentEditingQuestion,
        response: newResponse,
      }),
    });

    const data = await response.json();

    if (data.success) {
      // Check if this was a client entry moved to server
      if (data.data && data.data.source === 'client_to_server') {
        showStatus('Client cache entry moved to server and updated successfully!', 'success');

        // Remove from client cache if main chat page is open
        if (window.opener && window.opener.ResponseCache) {
          window.opener.ResponseCache.removeCachedResponse(currentEditingQuestion);
        }
      } else {
        showStatus('Response updated successfully!', 'success');
      }

      closeEditModal();
      loadCacheEntries(); // Refresh the list

      // Notify the main chat page to sync its cache
      if (window.opener && window.opener.syncFrontendCache) {
        window.opener.syncFrontendCache();
      }
    } else {
      showStatus(data.message, 'error');
    }
  } catch (error) {
    showStatus(`Error updating response: ${error.message}`, 'error');
  }
}

// Global audio storage
let currentAudio = null;
let currentQuestion = null;

// Toggle TTS for cache entry (play/stop)
async function toggleTTS(question) {
  const buttonId = `tts-btn-${question.replace(/[^a-zA-Z0-9]/g, '_')}`;
  const button = document.getElementById(buttonId);

  // If audio is currently playing for this question, stop it
  if (currentAudio && currentQuestion === question && !currentAudio.paused) {
    currentAudio.pause();
    currentAudio.currentTime = 0;
    currentAudio = null;
    currentQuestion = null;
    button.innerHTML = '🔊 Listen TTS';
    button.className = 'primary';
    showStatus('TTS audio stopped', 'info');
    return;
  }

  // If different audio is playing, stop it first
  if (currentAudio && currentQuestion !== question) {
    currentAudio.pause();
    currentAudio.currentTime = 0;
    const prevButtonId = `tts-btn-${currentQuestion.replace(/[^a-zA-Z0-9]/g, '_')}`;
    const prevButton = document.getElementById(prevButtonId);
    if (prevButton) {
      prevButton.innerHTML = '🔊 Listen TTS';
      prevButton.className = 'primary';
    }
  }

  try {
    showStatus('Generating TTS audio...', 'info');
    button.innerHTML = '⏳ Generating...';
    button.className = 'warning';

    const response = await fetch(`${API_BASE}/cache/listen-tts`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({ question: question }),
    });

    const data = await response.json();

    if (data.success) {
      // Create audio element and play the TTS
      currentAudio = new Audio(`data:audio/wav;base64,${data.data.audio}`);
      currentQuestion = question;

      // Update button to show stop state
      button.innerHTML = '⏹️ Stop TTS';
      button.className = 'danger';

      // Add event listeners for when audio ends
      currentAudio.addEventListener('ended', () => {
        currentAudio = null;
        currentQuestion = null;
        button.innerHTML = '🔊 Listen TTS';
        button.className = 'primary';
        showStatus('TTS audio finished', 'info');
      });

      currentAudio.addEventListener('error', () => {
        currentAudio = null;
        currentQuestion = null;
        button.innerHTML = '🔊 Listen TTS';
        button.className = 'primary';
        showStatus('TTS audio error', 'error');
      });

      currentAudio.play();
      showStatus('Playing TTS audio...', 'success');
    } else {
      button.innerHTML = '🔊 Listen TTS';
      button.className = 'primary';
      showStatus(data.message, 'error');
    }
  } catch (error) {
    button.innerHTML = '🔊 Listen TTS';
    button.className = 'primary';
    showStatus(`Error playing TTS: ${error.message}`, 'error');
  }
}

// Regenerate cache entry
async function regenerateEntry(question) {
  if (!confirm(`Are you sure you want to regenerate the cache entry for: "${question}"?`)) {
    return;
  }

  try {
    showStatus('Regenerating cache entry...', 'info');

    const response = await fetch(`${API_BASE}/cache/regenerate`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({ question: question }),
    });

    const data = await response.json();

    if (data.success) {
      showStatus(data.message, 'success');
      loadCacheStatus();
      loadCacheEntries();
    } else {
      showStatus(data.message, 'error');
    }
  } catch (error) {
    showStatus(`Error regenerating cache entry: ${error.message}`, 'error');
  }
}

// Regenerate TTS for cache entry
async function regenerateTTS(question) {
  try {
    showStatus('Regenerating TTS audio...', 'info');

    const response = await fetch(`${API_BASE}/cache/regenerate-tts`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({ question: question }),
    });

    const data = await response.json();

    if (data.success) {
      showStatus(data.message, 'success');
    } else {
      showStatus(data.message, 'error');
    }
  } catch (error) {
    showStatus(`Error regenerating TTS: ${error.message}`, 'error');
  }
}

// Regenerate all cache entries
async function regenerateAllCache() {
  if (!confirm('Are you sure you want to regenerate ALL cache entries? This may take a while.')) {
    return;
  }

  try {
    showStatus('Regenerating all cache entries...', 'info');

    const response = await fetch(`${API_BASE}/cache/regenerate-all`, {
      method: 'POST',
      headers: getAuthHeaders(),
    });

    const data = await response.json();

    if (data.success) {
      showStatus(data.message, 'success');
      loadCacheStatus();
      loadCacheEntries();
      loadCacheStats();
    } else {
      showStatus(data.message, 'error');
    }
  } catch (error) {
    showStatus(`Error regenerating all cache: ${error.message}`, 'error');
  }
}

// Update cache models
async function updateCacheModels() {
  if (
    !confirm(
      "This will update all cache entries that don't have model information with the current model. Continue?"
    )
  ) {
    return;
  }

  try {
    const response = await fetch(`${API_BASE}/cache/update-model`, {
      method: 'POST',
      headers: getAuthHeaders(),
    });

    const data = await response.json();

    if (data.success) {
      showStatus(data.message, 'success');
      loadCacheStatus();
      loadCacheEntries();
      loadCacheStats();
    } else {
      showStatus(data.message, 'error');
    }
  } catch (error) {
    showStatus(`Error updating cache models: ${error.message}`, 'error');
  }
}

// Clear all cache entries
async function clearAllCache() {
  if (!confirm('Are you sure you want to clear ALL cache entries? This action cannot be undone.')) {
    return;
  }

  try {
    const response = await fetch(`${API_BASE}/cache/clear`, {
      method: 'DELETE',
      headers: getAuthHeaders(),
    });

    const data = await response.json();

    if (data.success) {
      showStatus(data.message, 'success');
      loadCacheStatus();
      loadCacheEntries();
      loadCacheStats();
    } else {
      showStatus(data.message, 'error');
    }
  } catch (error) {
    showStatus(`Error clearing cache: ${error.message}`, 'error');
  }
}

// Load cache statistics
async function loadCacheStats() {
  // Loading cache stats
  try {
    const response = await fetch(`${API_BASE}/cache/status`, {
      headers: getAuthHeaders(),
    });

    // Cache stats response
    const data = await response.json();

    if (data.success) {
      const cacheData = data.data;

      // Calculate statistics
      const totalEntries = cacheData.total_entries || 0;
      const totalHits = cacheData.total_hits || 0;
      const totalMisses = cacheData.total_misses || 0;
      const hitRate =
        totalHits + totalMisses > 0
          ? ((totalHits / (totalHits + totalMisses)) * 100).toFixed(1) + '%'
          : '0%';

      // Estimate memory saved (rough calculation)
      const avgResponseSize = 500; // characters
      const memorySaved = totalHits * avgResponseSize;

      // Update UI
      document.getElementById('hit-rate').textContent = hitRate;
      document.getElementById('total-hits').textContent = totalHits;
      document.getElementById('total-misses').textContent = totalMisses;
      document.getElementById('memory-saved').textContent = formatBytes(memorySaved);

      // Load recent activity
      loadRecentActivity();
    } else {
      showStatus(data.message, 'error');
    }
  } catch (error) {
    showStatus(`Error loading cache stats: ${error.message}`, 'error');
  }
}

// Load recent activity
async function loadRecentActivity() {
  try {
    const response = await fetch(`${API_BASE}/cache/entries`, {
      headers: getAuthHeaders(),
    });

    const data = await response.json();

    if (data.success) {
      const activityLog = document.getElementById('recent-activity');
      const entries = data.data.entries || [];

      // Sort by timestamp (most recent first)
      entries.sort((a, b) => b.timestamp - a.timestamp);

      // Show last 10 entries
      const recentEntries = entries.slice(0, 10);
      activityLog.innerHTML = '';

      recentEntries.forEach((entry) => {
        const activityItem = document.createElement('div');
        activityItem.className = 'activity-item add';
        activityItem.innerHTML = `
          <strong>${entry.question}</strong><br>
          <small>Hits: ${entry.hit_count} | ${new Date(entry.timestamp).toLocaleString()}</small>
        `;
        activityLog.appendChild(activityItem);
      });
    }
  } catch (error) {
    // Error loading recent activity
  }
}

// Logout function
function logout() {
  sessionStorage.removeItem('cache_admin_username');
  sessionStorage.removeItem('cache_admin_password');
  window.location.href = '/cache/login';
}

// Initialize the page
document.addEventListener('DOMContentLoaded', function () {
  // Cache Admin Dashboard Initializing

  // Ensure modals are hidden on page load
  const responseModal = document.getElementById('response-modal');
  const editModal = document.getElementById('edit-modal');

  if (responseModal) {
    responseModal.style.display = 'none';
    // Response modal hidden
  }

  if (editModal) {
    editModal.style.display = 'none';
    // Edit modal hidden
  }

  // Check authentication
  if (!checkAuthentication()) {
    return;
  }

  // Debug: Check if tabs exist
  const tabs = document.querySelectorAll('.tab-btn');
  // Found tabs
  tabs.forEach((tab, index) => {
    // Tab info
  });

  // Debug: Check if tab content exists
  const tabContents = document.querySelectorAll('.tab-content');
  // Found tab contents
  tabContents.forEach((content, index) => {
    // Content info
  });

  // Load initial data
  loadCacheStatus();
  loadCacheEntries();
  loadCacheStats();

  // Close modals when clicking outside
  window.onclick = function (event) {
    const responseModal = document.getElementById('response-modal');
    const editModal = document.getElementById('edit-modal');

    if (event.target === responseModal) {
      closeResponseModal();
    }
    if (event.target === editModal) {
      closeEditModal();
    }
  };

  // Close modals with Escape key
  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape') {
      closeResponseModal();
      closeEditModal();
    }
  });

  // Cache Admin Dashboard Ready
});
 