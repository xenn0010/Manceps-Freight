export function truckSvg(color, heading) {
  return `<svg viewBox="0 0 44 44" width="44" height="44" style="transform: rotate(${heading}deg)" aria-hidden="true">
  <path d="M22 1.5 L27.5 9 H16.5 Z" fill="${color}"/>
  <circle cx="22" cy="22" r="13" fill="#fff" stroke="${color}" stroke-width="2.5"/>
  <rect x="18.2" y="18.6" width="7.6" height="12" rx="1.6" fill="${color}"/>
  <rect x="18.8" y="13.6" width="6.4" height="4" rx="1.4" fill="${color}" opacity="0.7"/>
</svg>`;
}
