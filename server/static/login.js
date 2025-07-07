document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('login-form');
  const errorDiv = document.getElementById('error-msg');

  // Make chat bubbles dismissable using event delegation
  const chatBubblesContainer = document.querySelector('.chat-bubbles');

  // Function to dismiss a bubble with animation
  function dismissBubble(bubble) {
    console.log('Dismissing bubble:', bubble); // Debug log
    bubble.style.transition = 'all 0.3s ease-out';
    bubble.style.transform = 'translateY(-20px) scale(0.8)';
    bubble.style.opacity = '0';
    bubble.style.pointerEvents = 'none'; // Prevent multiple clicks

    setTimeout(() => {
      if (bubble.parentNode) {
        bubble.remove();
      }
    }, 300);
  }

  // Use event delegation to handle clicks on bubbles
  if (chatBubblesContainer) {
    let touchStartTime = 0;
    let touchStartTarget = null;

    // Handle click events (desktop)
    chatBubblesContainer.addEventListener('click', (e) => {
      const bubble = e.target.closest('.chat-bubble');
      if (bubble && !touchStartTarget) {
        // Only if not from touch
        console.log('Bubble clicked:', bubble); // Debug log
        dismissBubble(bubble);
      }
    });

    // Handle touch start
    chatBubblesContainer.addEventListener('touchstart', (e) => {
      const bubble = e.target.closest('.chat-bubble');
      if (bubble) {
        console.log('Bubble touchstart:', bubble); // Debug log
        touchStartTime = Date.now();
        touchStartTarget = bubble;
        // Add visual feedback
        bubble.style.transform = 'scale(0.95)';
        bubble.style.transition = 'transform 0.1s ease';
      }
    });

    // Handle touch end
    chatBubblesContainer.addEventListener('touchend', (e) => {
      const bubble = e.target.closest('.chat-bubble');
      if (bubble && touchStartTarget === bubble) {
        console.log('Bubble touchend:', bubble); // Debug log
        const touchDuration = Date.now() - touchStartTime;

        // Only dismiss if it was a quick tap (not a long press or scroll)
        if (touchDuration < 500) {
          e.preventDefault(); // Prevent click event from firing
          dismissBubble(bubble);
        } else {
          // Reset visual feedback if it was a long press
          bubble.style.transform = '';
        }
      }

      // Reset touch tracking
      touchStartTarget = null;
      touchStartTime = 0;
    });

    // Handle touch cancel (when user drags away)
    chatBubblesContainer.addEventListener('touchcancel', (e) => {
      if (touchStartTarget) {
        // Reset visual feedback
        touchStartTarget.style.transform = '';
        touchStartTarget = null;
        touchStartTime = 0;
      }
    });

    // Add cursor pointer to all bubbles after they're loaded
    setTimeout(() => {
      const bubbles = document.querySelectorAll('.chat-bubble');
      bubbles.forEach((bubble) => {
        bubble.style.cursor = 'pointer';
      });
    }, 100);
  }

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
