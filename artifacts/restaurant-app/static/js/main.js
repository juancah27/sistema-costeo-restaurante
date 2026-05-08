document.addEventListener('DOMContentLoaded', () => {
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('overlay');
  const mainEl  = document.getElementById('main');
  const hamBtn   = document.getElementById('hamburger');
  let sidebarOpen = window.innerWidth > 768;

  function setSidebar(open) {
    sidebarOpen = open;
    if (open) {
      sidebar.classList.remove('hidden');
      overlay.classList.toggle('show', window.innerWidth <= 768);
      mainEl.classList.remove('expanded');
    } else {
      sidebar.classList.add('hidden');
      overlay.classList.remove('show');
      mainEl.classList.add('expanded');
    }
  }

  if (hamBtn) {
    hamBtn.addEventListener('click', () => setSidebar(!sidebarOpen));
  }
  if (overlay) {
    overlay.addEventListener('click', () => setSidebar(false));
  }

  // Initial state
  if (window.innerWidth <= 768) setSidebar(false);

  // Auto-dismiss alerts
  document.querySelectorAll('.alert').forEach(el => {
    setTimeout(() => {
      el.style.transition = 'opacity .4s';
      el.style.opacity = '0';
      setTimeout(() => el.remove(), 400);
    }, 3500);
  });

  // Inline edit rows toggle
  document.querySelectorAll('[data-edit-toggle]').forEach(btn => {
    btn.addEventListener('click', () => {
      const rowId = btn.dataset.editToggle;
      const editRow = document.getElementById('edit-' + rowId);
      if (editRow) {
        editRow.classList.toggle('show');
      }
    });
  });

  // Confirm delete
  document.querySelectorAll('[data-confirm]').forEach(form => {
    form.addEventListener('submit', e => {
      if (!confirm(form.dataset.confirm || '¿Confirmar acción?')) {
        e.preventDefault();
      }
    });
  });
});
