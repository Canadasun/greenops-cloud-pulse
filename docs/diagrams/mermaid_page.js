// Renders the Mermaid text in <pre id="src"> into #d, then appends an optional legend (window.LEGEND).
// Loaded after node_modules/mermaid/dist/mermaid.min.js (see package.json).
mermaid.initialize({ startOnLoad: false, securityLevel: 'loose', theme: 'base', fontFamily: 'Calibri, Carlito, Arial, sans-serif',
  themeVariables: { fontSize: '19px', primaryColor: '#e8f0fb', primaryBorderColor: '#2E5496', primaryTextColor: '#1a1a19', lineColor: '#3a3a36',
    clusterBkg: '#f6f8fc', clusterBorder: '#1F3864', edgeLabelBackground: '#ffffff', tertiaryColor: '#fff' },
  flowchart: { curve: 'basis', nodeSpacing: 30, rankSpacing: 30, padding: 10, htmlLabels: true, useMaxWidth: false, wrappingWidth: 460 },
  class: { useMaxWidth: false }, sequence: { useMaxWidth: false, messageFontSize: 17, actorFontSize: 17, noteFontSize: 16 }, er: { useMaxWidth: false, fontSize: 17 } });
(async () => {
  const { svg } = await mermaid.render('m', document.getElementById('src').textContent);
  const d = document.getElementById('d');
  d.insertAdjacentHTML('beforeend', svg);
  if (window.LEGEND) {
    const box = document.createElement('div'); box.className = 'legend';
    box.innerHTML = '<b>How to read this diagram</b>' + window.LEGEND.map((l) => '<div>• ' + l + '</div>').join('');
    d.appendChild(box);
  }
  window.READY = true;
})();
