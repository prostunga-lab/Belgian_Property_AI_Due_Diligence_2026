/* Behaviour of the site. Served from /static so the Content-Security-Policy can forbid inline scripts. */
document.documentElement.classList.add("js");
document.addEventListener("click",function(e){
  var b=e.target.closest(".pwtoggle"); if(!b) return;
  var input=b.parentElement.querySelector("input"), show=input.type==="password";
  input.type=show?"text":"password";
  b.setAttribute("aria-pressed",show?"true":"false");
  var label=show?b.dataset.hide:b.dataset.show; b.setAttribute("aria-label",label); b.title=label;
});
// Never leave a password visible when coming back to the page (back button / bfcache).
window.addEventListener("pageshow",function(){
  document.querySelectorAll(".pwtoggle").forEach(function(b){
    var input=b.parentElement.querySelector("input"); input.type="password";
    b.setAttribute("aria-pressed","false"); b.setAttribute("aria-label",b.dataset.show); b.title=b.dataset.show;
  });
});

// Confirmation before destructive actions: <form data-confirm="message">.
document.addEventListener("submit", function (e) {
  var message = e.target.getAttribute && e.target.getAttribute("data-confirm");
  if (message && !window.confirm(message)) e.preventDefault();
});
// <select data-autosubmit> submits its form when changed.
document.addEventListener("change", function (e) {
  if (e.target.matches && e.target.matches("select[data-autosubmit]")) e.target.form.submit();
});
// <a data-back href="/"> goes back in the history when there is one.
document.addEventListener("click", function (e) {
  var a = e.target.closest && e.target.closest("a[data-back]");
  if (a && window.history.length > 1) { e.preventDefault(); window.history.back(); }
});
