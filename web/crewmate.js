'use strict';
// Original crewmate style characters drawn as inline SVG. Not based on any official artwork files.
(function () {
  const COLORS = [
    { name: 'Red', c: '#d6242a' },
    { name: 'Blue', c: '#2a53e0' },
    { name: 'Green', c: '#1b9a36' },
    { name: 'Pink', c: '#f062c0' },
    { name: 'Orange', c: '#f5851d' },
    { name: 'Yellow', c: '#f4e04d' },
    { name: 'Black', c: '#4a525c' },
    { name: 'White', c: '#dfe7f2' },
    { name: 'Purple', c: '#7b3fc9' },
    { name: 'Cyan', c: '#3fe6d0' },
  ];

  const BODY =
    'M22 50 C22 22 38 10 54 10 C72 10 82 26 82 50 L82 96 Q82 106 72 106 L62 106 Q56 106 56 98 ' +
    'L56 92 L48 92 L48 98 Q48 106 40 106 L32 106 Q22 106 22 96 Z';
  const INK = '#14141c';

  function shade(hex, amount) {
    const n = parseInt(hex.slice(1), 16);
    const f = (v) => Math.max(0, Math.round(v * (1 - amount)));
    const r = f((n >> 16) & 255), g = f((n >> 8) & 255), b = f(n & 255);
    return '#' + [r, g, b].map((v) => v.toString(16).padStart(2, '0')).join('');
  }

  // Shared clip paths, referenced by every character. Must live in the DOM (not display: none).
  function ensureDefs() {
    if (document.getElementById('crew-defs')) return;
    const holder = document.createElement('div');
    holder.id = 'crew-defs';
    holder.setAttribute('aria-hidden', 'true');
    holder.style.cssText = 'position:absolute;width:0;height:0;overflow:hidden';
    holder.innerHTML =
      '<svg width="0" height="0"><defs>' +
      '<clipPath id="cm-body"><path d="' + BODY + '"/></clipPath>' +
      '<clipPath id="cm-lower"><rect x="0" y="64" width="100" height="60"/></clipPath>' +
      '</defs></svg>';
    document.body.appendChild(holder);
  }

  function svg(hex, opts) {
    const dead = !!(opts && opts.dead);
    const pack = shade(hex, 0.3);
    const parts =
      '<rect x="6" y="52" width="18" height="44" rx="8" fill="' + pack + '" stroke="' + INK + '" stroke-width="3"/>' +
      '<path d="' + BODY + '" fill="' + hex + '" stroke="' + INK + '" stroke-width="3" stroke-linejoin="round"/>' +
      '<g clip-path="url(#cm-body)">' +
      '<rect x="0" y="72" width="100" height="50" fill="rgba(0,0,0,.22)"/>' +
      '<ellipse cx="38" cy="22" rx="11" ry="5" fill="rgba(255,255,255,.35)" transform="rotate(-20 38 22)"/>' +
      '</g>';
    if (!dead) {
      return (
        '<svg viewBox="0 0 100 120" xmlns="http://www.w3.org/2000/svg" role="img">' +
        parts +
        '<rect x="44" y="26" width="36" height="26" rx="12" fill="#9fe6ff" stroke="' + INK + '" stroke-width="3"/>' +
        '<rect x="50" y="30" width="15" height="6" rx="3" fill="rgba(255,255,255,.85)"/>' +
        '</svg>'
      );
    }
    // Dead: only the lower half remains, with a bone sticking out of the cut.
    return (
      '<svg viewBox="0 0 100 120" xmlns="http://www.w3.org/2000/svg" role="img">' +
      '<g clip-path="url(#cm-lower)">' + parts +
      '<g clip-path="url(#cm-body)"><rect x="20" y="64" width="64" height="7" fill="#e9d3c0"/></g>' +
      '</g>' +
      '<rect x="46" y="50" width="8" height="18" rx="4" fill="#f4ecd5" stroke="' + INK + '" stroke-width="2.5"/>' +
      '<circle cx="45" cy="51" r="4.5" fill="#f4ecd5" stroke="' + INK + '" stroke-width="2.5"/>' +
      '<circle cx="55" cy="51" r="4.5" fill="#f4ecd5" stroke="' + INK + '" stroke-width="2.5"/>' +
      '</svg>'
    );
  }

  window.Crew = { COLORS, svg, ensureDefs };
})();
