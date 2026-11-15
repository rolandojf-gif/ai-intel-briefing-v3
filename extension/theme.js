// Se carga en <head>, antes de pintar: aplica el tema guardado sin parpadeo.
// Va en fichero aparte porque las paginas de extension (MV3) no ejecutan <script> en linea.
(function () {
  try {
    var t = localStorage.getItem('theme');
    if (t === 'light' || t === 'dark') document.documentElement.setAttribute('data-theme', t);
  } catch (e) { /* sin almacenamiento: tema del sistema */ }
})();
