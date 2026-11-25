/* Printable report: the button opens the browser's print dialog, where "Save as PDF" is a destination. */
(function () {
  'use strict';
  var b = document.getElementById('printBtn');
  if (b) b.addEventListener('click', function () { window.print(); });
})();
