document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('login-form');
  const errorDiv = document.getElementById('error-msg');

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const username = document.getElementById('username').value.trim();
    const password = document.getElementById('password').value.trim();

    try {
      const res = await fetch('/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({ username, password }),
      });

      const data = await res.json();

      if (!res.ok) throw new Error(data.detail || 'Login failed');

      // No need to store token manually – it's set as cookie by server
      window.location.href = '/'; // Redirect to homepage
    } catch (err) {
      errorDiv.textContent = err.message;
    }
  });
});
