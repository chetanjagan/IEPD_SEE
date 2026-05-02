/* ═══════════════════════════════════════════════════
   VEGNUTRI — PREMIUM UI ENHANCEMENTS JS
   Particles, Scroll Reveal, Counter Animations
═══════════════════════════════════════════════════ */

// ── PARTICLES BACKGROUND ──────────────────────
(function initParticles() {
  const canvas = document.createElement('canvas');
  canvas.id = 'particles-canvas';
  document.body.prepend(canvas);
  const ctx = canvas.getContext('2d');
  let w, h, particles = [];
  const PARTICLE_COUNT = 35;

  function resize() {
    w = canvas.width = window.innerWidth;
    h = canvas.height = window.innerHeight;
  }
  resize();
  window.addEventListener('resize', resize);

  class Particle {
    constructor() { this.reset(); }
    reset() {
      this.x = Math.random() * w;
      this.y = Math.random() * h;
      this.r = Math.random() * 2.5 + 0.8;
      this.vx = (Math.random() - 0.5) * 0.3;
      this.vy = (Math.random() - 0.5) * 0.3;
      this.alpha = Math.random() * 0.4 + 0.1;
      const colors = ['106,191,138', '217,119,6', '45,125,210', '143,212,166'];
      this.color = colors[Math.floor(Math.random() * colors.length)];
    }
    update() {
      this.x += this.vx;
      this.y += this.vy;
      if (this.x < -10 || this.x > w + 10 || this.y < -10 || this.y > h + 10) this.reset();
    }
    draw() {
      ctx.beginPath();
      ctx.arc(this.x, this.y, this.r, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(${this.color},${this.alpha})`;
      ctx.fill();
    }
  }

  for (let i = 0; i < PARTICLE_COUNT; i++) particles.push(new Particle());

  function animate() {
    ctx.clearRect(0, 0, w, h);
    particles.forEach(p => { p.update(); p.draw(); });
    // Draw lines between close particles
    for (let i = 0; i < particles.length; i++) {
      for (let j = i + 1; j < particles.length; j++) {
        const dx = particles[i].x - particles[j].x;
        const dy = particles[i].y - particles[j].y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < 150) {
          ctx.beginPath();
          ctx.moveTo(particles[i].x, particles[i].y);
          ctx.lineTo(particles[j].x, particles[j].y);
          ctx.strokeStyle = `rgba(106,191,138,${0.06 * (1 - dist / 150)})`;
          ctx.lineWidth = 0.5;
          ctx.stroke();
        }
      }
    }
    requestAnimationFrame(animate);
  }
  animate();
})();

// ── SCROLL REVEAL ──────────────────────────────
(function initScrollReveal() {
  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('revealed');
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.1, rootMargin: '0px 0px -40px 0px' });

  document.addEventListener('DOMContentLoaded', () => {
    // Add reveal class to elements below the fold
    const selectors = [
      '.features .feature-card',
      '.cta h2', '.cta p', '.cta .btn',
      '.tip-card', '.mi', '.hi-row', '.why-item',
      '.target-row', '.mood-insight-card'
    ];
    selectors.forEach(sel => {
      document.querySelectorAll(sel).forEach(el => {
        el.classList.add('reveal-on-scroll');
        observer.observe(el);
      });
    });
  });
})();

// ── ANIMATED COUNTERS ──────────────────────────
(function initCounters() {
  function animateValue(el, start, end, duration) {
    const range = end - start;
    const isDecimal = String(end).includes('.');
    let startTime = null;
    function tick(ts) {
      if (!startTime) startTime = ts;
      const progress = Math.min((ts - startTime) / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3); // ease-out cubic
      const current = start + range * eased;
      el.textContent = isDecimal ? current.toFixed(1) : Math.round(current);
      if (progress < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  }

  document.addEventListener('DOMContentLoaded', () => {
    // Animate stat numbers
    document.querySelectorAll('.stat-nums, .stat-val, .consistency-score, .bmi-number, .ach-pct').forEach(el => {
      const text = el.textContent.trim();
      const match = text.match(/^([\d.]+)/);
      if (match) {
        const target = parseFloat(match[1]);
        const suffix = text.substring(match[1].length);
        const observer = new IntersectionObserver((entries) => {
          entries.forEach(entry => {
            if (entry.isIntersecting) {
              const origText = el.textContent;
              animateValue(el, 0, target, 800);
              // Restore suffix after animation
              setTimeout(() => {
                el.textContent = match[1] + suffix;
              }, 850);
              observer.unobserve(el);
            }
          });
        }, { threshold: 0.5 });
        observer.observe(el);
      }
    });
  });
})();

// ── SMOOTH PAGE TRANSITIONS ────────────────────
(function initPageTransitions() {
  document.addEventListener('DOMContentLoaded', () => {
    document.body.style.opacity = '0';
    document.body.style.transition = 'opacity .35s ease';
    requestAnimationFrame(() => {
      document.body.style.opacity = '1';
    });
  });
})();

// ── TILT EFFECT ON STAT CARDS ──────────────────
(function initTiltEffect() {
  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.stat-card, .action-btn').forEach(card => {
      card.addEventListener('mousemove', (e) => {
        const rect = card.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        const centerX = rect.width / 2;
        const centerY = rect.height / 2;
        const rotateX = (y - centerY) / centerY * -3;
        const rotateY = (x - centerX) / centerX * 3;
        card.style.transform = `perspective(500px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) translateY(-2px)`;
      });
      card.addEventListener('mouseleave', () => {
        card.style.transform = '';
      });
    });
  });
})();

// ── ENHANCED DARK MODE TOGGLE ──────────────────
(function enhanceDarkToggle() {
  const orig = window.toggleDarkMode;
  window.toggleDarkMode = function() {
    document.body.style.transition = 'background .5s ease, color .3s ease';
    if (orig) orig();
    setTimeout(() => { document.body.style.transition = ''; }, 600);
  };
})();
