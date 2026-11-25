/* Account deletion on the privacy page. Asks for the password, then erases everything. */
(function () {
  'use strict';
  const form = document.getElementById('delForm');
  if (!form) return;
  const msg = document.getElementById('delMsg');
  form.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    if (!confirm('Delete the account and everything in it? This cannot be undone.')) return;
    msg.textContent = '';
    try {
      const r = await fetch('/api/account/delete', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password: document.getElementById('delPass').value }) });
      const j = await r.json().catch(() => ({}));
      if (!r.ok) { msg.textContent = j.error || 'Could not delete the account.'; return; }
      form.innerHTML = '<p>The account and everything in it have been deleted.</p>';
    } catch (_) { msg.textContent = 'Could not reach the server.'; }
  });
})();
