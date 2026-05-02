/* VegNutri V5 */

// ── Dark mode (apply before paint) ───────────
(function() {
  if (localStorage.getItem('vn_theme') === 'dark')
    document.documentElement.setAttribute('data-theme', 'dark');
})();

function toggleDarkMode() {
  const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
  document.documentElement.setAttribute('data-theme', isDark ? '' : 'dark');
  localStorage.setItem('vn_theme', isDark ? 'light' : 'dark');
}

// ── Sidebar collapse (desktop) ────────────────
function toggleSidebar() {
  const sb = document.getElementById('sidebar');
  const mc = document.getElementById('mainContent');
  if (!sb) return;
  const collapsed = sb.classList.toggle('collapsed');
  if (mc) mc.classList.toggle('collapsed', collapsed);
  localStorage.setItem('vn_sidebar', collapsed ? 'collapsed' : 'open');
}

// Restore sidebar state on desktop
document.addEventListener('DOMContentLoaded', () => {
  const sb = document.getElementById('sidebar');
  const mc = document.getElementById('mainContent');
  if (sb && window.innerWidth > 768) {
    if (localStorage.getItem('vn_sidebar') === 'collapsed') {
      sb.classList.add('collapsed');
      if (mc) mc.classList.add('collapsed');
    }
  }
});

// ── Mobile sidebar ────────────────────────────
function openMobileSidebar() {
  document.getElementById('sidebar')?.classList.add('mobile-open');
  document.getElementById('sidebarOverlay')?.classList.add('visible');
  document.body.style.overflow = 'hidden';
}

function closeMobileSidebar() {
  document.getElementById('sidebar')?.classList.remove('mobile-open');
  document.getElementById('sidebarOverlay')?.classList.remove('visible');
  document.body.style.overflow = '';
}

// ── Flash auto-dismiss ────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  setTimeout(() => {
    document.querySelectorAll('.flash').forEach(el => {
      el.style.transition = 'opacity .5s, transform .5s';
      el.style.opacity = '0';
      el.style.transform = 'translateX(110%)';
      setTimeout(() => el.remove(), 500);
    });
  }, 4500);
});
