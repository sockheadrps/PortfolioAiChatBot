// Configuration
const API_BASE = '';

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

// Show loading state
function showLoading(show = true) {
  const loadingDiv = document.getElementById('loading');
  const loginBtn = document.getElementById('login-btn');

  if (loadingDiv) {
    loadingDiv.classList.toggle('show', show);
  }

  if (loginBtn) {
    loginBtn.disabled = show;
    loginBtn.textContent = show ? 'Logging in...' : 'Login';
  }
}

// Handle login form submission
async function handleLogin(event) {
  event.preventDefault();

  const username = document.getElementById('username').value.trim();
  const password = document.getElementById('password').value.trim();

  if (!username || !password) {
    showStatus('Please enter both username and password', 'error');
    return;
  }

  showLoading(true);

  try {
    // Test authentication by making a request to a protected endpoint
    const response = await fetch(`${API_BASE}/cache/status`, {
      headers: {
        Authorization: `Basic ${btoa(`${username}:${password}`)}`,
        'Content-Type': 'application/json',
      },
    });

    if (response.ok) {
      // Store credentials in sessionStorage
      sessionStorage.setItem('cache_admin_username', username);
      sessionStorage.setItem('cache_admin_password', password);

      showStatus('Login successful! Redirecting...', 'success');

      // Redirect to admin dashboard after a short delay
      setTimeout(() => {
        window.location.href = '/cache/admin';
      }, 1000);
    } else {
      showStatus('Invalid username or password', 'error');
    }
  } catch (error) {
    console.error('Login error:', error);
    showStatus('Login failed. Please try again.', 'error');
  } finally {
    showLoading(false);
  }
}

// Initialize the page
document.addEventListener('DOMContentLoaded', function () {
  // Cache Login Page Initializing

  // Check if user is already logged in
  const username = sessionStorage.getItem('cache_admin_username');
  const password = sessionStorage.getItem('cache_admin_password');

  if (username && password) {
    // User already logged in, redirecting to admin dashboard
    window.location.href = '/cache/admin';
    return;
  }

  // Add form submission handler
  const loginForm = document.getElementById('login-form');
  if (loginForm) {
    loginForm.addEventListener('submit', handleLogin);
  }

  // Add Enter key handler for form submission
  document.addEventListener('keydown', function (event) {
    if (event.key === 'Enter') {
      const loginForm = document.getElementById('login-form');
      if (loginForm) {
        handleLogin(event);
      }
    }
  });

  // Cache Login Page Ready
});
 