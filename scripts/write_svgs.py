"""Write vivid SVG thumbnails with high-contrast, clearly visible colors."""
import os

base = r'c:\Users\Christian\Documents\Projects\mvp_chat\frontend\img'

iu = r"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 450">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" stop-color="#5b21b6"/>
      <stop offset="100%" stop-color="#7c3aed"/>
    </linearGradient>
    <filter id="gf"><feGaussianBlur stdDeviation="4" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
  </defs>
  <rect width="800" height="450" fill="url(#bg)"/>
  <rect x="0" y="295" width="800" height="155" fill="#3b0764" opacity="0.85"/>
  <rect x="0" y="260" width="800" height="28" fill="#fde047" opacity="0.95"/>
  <text x="20" y="280" font-family="Arial Black,sans-serif" font-size="13" fill="#1e1b4b" font-weight="900" letter-spacing="6">POLICE LINE DO NOT CROSS  POLICE LINE DO NOT CROSS  POLICE LINE</text>
  <rect x="0" y="300" width="800" height="18" fill="#fde047" opacity="0.82"/>
  <rect x="250" y="55" width="300" height="235" fill="#2e1065" opacity="0.9" rx="4"/>
  <line x1="400" y1="55" x2="400" y2="290" stroke="#3b0764" stroke-width="12"/>
  <line x1="250" y1="165" x2="550" y2="165" stroke="#3b0764" stroke-width="12"/>
  <rect x="260" y="65" width="132" height="92" fill="#a78bfa" opacity="0.22"/>
  <ellipse cx="400" cy="130" rx="30" ry="34" fill="#1e1b4b"/>
  <rect x="370" y="164" width="60" height="85" fill="#1e1b4b" rx="8"/>
  <polygon points="330,308 344,288 358,308" fill="#ef4444"/>
  <text x="333" y="306" font-family="Arial,sans-serif" font-size="12" fill="white" font-weight="bold">1</text>
  <polygon points="438,316 452,296 466,316" fill="#ef4444"/>
  <text x="441" y="314" font-family="Arial,sans-serif" font-size="12" fill="white" font-weight="bold">2</text>
  <rect x="0" y="0" width="8" height="450" fill="#c026d3" opacity="0.7"/>
  <rect x="792" y="0" width="8" height="450" fill="#c026d3" opacity="0.5"/>
  <rect x="0" y="370" width="800" height="80" fill="#1e1b4b" opacity="0.82"/>
  <text x="400" y="410" font-family="Georgia,serif" font-size="30" fill="#ede9fe" text-anchor="middle" font-weight="bold">IU: Murder Mystery</text>
  <text x="400" y="435" font-family="Arial,sans-serif" font-size="13" fill="#c4b5fd" text-anchor="middle" letter-spacing="4">CRIME DRAMA</text>
</svg>"""

jennie = r"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 450">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" stop-color="#9d174d"/>
      <stop offset="100%" stop-color="#be185d"/>
    </linearGradient>
    <radialGradient id="spot" cx="50%" cy="60%" r="38%">
      <stop offset="0%" stop-color="#f9a8d4" stop-opacity="0.45"/>
      <stop offset="100%" stop-color="#9d174d" stop-opacity="0"/>
    </radialGradient>
    <filter id="gf"><feGaussianBlur stdDeviation="6" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
  </defs>
  <rect width="800" height="450" fill="url(#bg)"/>
  <rect width="800" height="450" fill="url(#spot)"/>
  <rect x="0" y="315" width="800" height="135" fill="#500724" opacity="0.8"/>
  <polygon points="350,0 320,0 370,315 400,315" fill="#fda4af" opacity="0.10"/>
  <polygon points="450,0 480,0 430,315 400,315" fill="#fda4af" opacity="0.10"/>
  <polygon points="400,0 382,0 392,315 408,315" fill="#ffffff" opacity="0.08"/>
  <ellipse cx="380" cy="335" rx="75" ry="22" fill="#f472b6" opacity="0.28" filter="url(#gf)"/>
  <ellipse cx="430" cy="332" rx="70" ry="20" fill="#f472b6" opacity="0.22" filter="url(#gf)"/>
  <rect x="396" y="172" width="8" height="143" fill="#c77daa" opacity="0.8"/>
  <ellipse cx="400" cy="170" rx="22" ry="12" fill="#e879a0" opacity="0.9"/>
  <ellipse cx="400" cy="215" rx="24" ry="28" fill="#4a0520"/>
  <rect x="376" y="243" width="48" height="74" fill="#4a0520" rx="7"/>
  <rect x="0" y="0" width="125" height="450" fill="#6b0033" opacity="0.6"/>
  <rect x="675" y="0" width="125" height="450" fill="#6b0033" opacity="0.6"/>
  <rect x="0" y="15" width="800" height="10" fill="#7f1d3f" opacity="0.7"/>
  <ellipse cx="270" cy="15" rx="9" ry="11" fill="#fbbf24" opacity="0.8"/>
  <ellipse cx="370" cy="15" rx="9" ry="11" fill="#f472b6" opacity="0.9"/>
  <ellipse cx="430" cy="15" rx="9" ry="11" fill="#f472b6" opacity="0.9"/>
  <ellipse cx="530" cy="15" rx="9" ry="11" fill="#fbbf24" opacity="0.8"/>
  <rect x="0" y="0" width="6" height="450" fill="#f472b6" opacity="0.65"/>
  <rect x="794" y="0" width="6" height="450" fill="#f472b6" opacity="0.5"/>
  <rect x="0" y="368" width="800" height="82" fill="#500724" opacity="0.8"/>
  <text x="400" y="408" font-family="Georgia,serif" font-size="30" fill="#fce7f3" text-anchor="middle" font-weight="bold">Jennie: Blackout</text>
  <text x="400" y="433" font-family="Arial,sans-serif" font-size="13" fill="#f9a8d4" text-anchor="middle" letter-spacing="4">K-DRAMA THRILLER</text>
</svg>"""

blackout = r"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 450">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" stop-color="#134e4a"/>
      <stop offset="100%" stop-color="#0f766e"/>
    </linearGradient>
    <radialGradient id="moon" cx="62%" cy="16%" r="16%">
      <stop offset="0%" stop-color="#f0fdf4" stop-opacity="1.0"/>
      <stop offset="100%" stop-color="#134e4a" stop-opacity="0"/>
    </radialGradient>
    <filter id="gf"><feGaussianBlur stdDeviation="5" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
  </defs>
  <rect width="800" height="450" fill="url(#bg)"/>
  <rect width="800" height="450" fill="url(#moon)"/>
  <circle cx="498" cy="72" r="48" fill="#ecfdf5" opacity="0.92" filter="url(#gf)"/>
  <circle cx="514" cy="60" r="42" fill="#0d3b38" opacity="0.6"/>
  <ellipse cx="180" cy="62" rx="155" ry="42" fill="#0f5954" opacity="0.75"/>
  <ellipse cx="660" cy="42" rx="170" ry="36" fill="#0f5954" opacity="0.65"/>
  <rect x="185" y="165" width="430" height="260" fill="#052420"/>
  <polygon points="185,165 400,68 615,165" fill="#052420"/>
  <rect x="168" y="142" width="85" height="118" fill="#052420"/>
  <polygon points="168,142 210,104 252,142" fill="#052420"/>
  <rect x="547" y="142" width="85" height="118" fill="#052420"/>
  <polygon points="547,142 589,104 631,142" fill="#052420"/>
  <rect x="376" y="44" width="48" height="90" fill="#052420"/>
  <polygon points="376,44 400,12 424,44" fill="#052420"/>
  <rect x="282" y="192" width="54" height="70" fill="#f59e0b" opacity="0.78"/>
  <rect x="364" y="186" width="64" height="76" fill="#fbbf24" opacity="0.68"/>
  <rect x="458" y="192" width="54" height="70" fill="#f59e0b" opacity="0.58"/>
  <rect x="376" y="56" width="48" height="58" fill="#fcd34d" opacity="0.48"/>
  <rect x="0" y="392" width="800" height="58" fill="#052420"/>
  <polyline points="510,8 486,96 520,96 490,185" stroke="#bbf7d0" stroke-width="4" fill="none" opacity="0.9" filter="url(#gf)"/>
  <rect x="0" y="0" width="6" height="450" fill="#2dd4bf" opacity="0.55"/>
  <rect x="794" y="0" width="6" height="450" fill="#2dd4bf" opacity="0.4"/>
  <rect x="0" y="368" width="800" height="82" fill="#052420" opacity="0.85"/>
  <text x="400" y="408" font-family="Georgia,serif" font-size="30" fill="#ccfbf1" text-anchor="middle" font-weight="bold">Blackout Manor</text>
  <text x="400" y="433" font-family="Arial,sans-serif" font-size="13" fill="#5eead4" text-anchor="middle" letter-spacing="4">GOTHIC MYSTERY</text>
</svg>"""

neon = r"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 450">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" stop-color="#1e1b4b"/>
      <stop offset="100%" stop-color="#312e81"/>
    </linearGradient>
    <filter id="glow"><feGaussianBlur stdDeviation="5" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
  </defs>
  <rect width="800" height="450" fill="url(#bg)"/>
  <rect x="0" y="102" width="92" height="348" fill="#16133a"/>
  <rect x="102" y="140" width="72" height="310" fill="#120f30"/>
  <rect x="184" y="82" width="102" height="368" fill="#16133a"/>
  <rect x="296" y="120" width="82" height="330" fill="#120f30"/>
  <rect x="388" y="90" width="92" height="360" fill="#16133a"/>
  <rect x="490" y="60" width="112" height="390" fill="#120f30"/>
  <rect x="612" y="108" width="92" height="342" fill="#16133a"/>
  <rect x="714" y="82" width="86" height="368" fill="#120f30"/>
  <rect x="12" y="122" width="24" height="16" fill="#60a5fa" opacity="0.7"/>
  <rect x="46" y="122" width="24" height="16" fill="#60a5fa" opacity="0.5"/>
  <rect x="196" y="102" width="26" height="18" fill="#818cf8" opacity="0.65"/>
  <rect x="398" y="112" width="28" height="18" fill="#a78bfa" opacity="0.6"/>
  <rect x="500" y="80" width="30" height="20" fill="#60a5fa" opacity="0.65"/>
  <rect x="540" y="80" width="30" height="20" fill="#60a5fa" opacity="0.5"/>
  <rect x="298" y="144" width="84" height="16" fill="#f0abfc" opacity="0.98" filter="url(#glow)"/>
  <rect x="392" y="114" width="86" height="14" fill="#67e8f9" opacity="0.96" filter="url(#glow)"/>
  <rect x="196" y="122" width="70" height="12" fill="#fb923c" opacity="0.94" filter="url(#glow)"/>
  <rect x="12" y="172" width="74" height="13" fill="#f0abfc" opacity="0.96" filter="url(#glow)"/>
  <rect x="102" y="196" width="60" height="11" fill="#34d399" opacity="0.92" filter="url(#glow)"/>
  <rect x="500" y="104" width="92" height="14" fill="#f472b6" opacity="0.97" filter="url(#glow)"/>
  <rect x="620" y="144" width="72" height="13" fill="#38bdf8" opacity="0.93" filter="url(#glow)"/>
  <rect x="722" y="114" width="60" height="12" fill="#fbbf24" opacity="0.9" filter="url(#glow)"/>
  <rect x="0" y="355" width="800" height="95" fill="#06050f"/>
  <rect x="298" y="362" width="84" height="7" fill="#f0abfc" opacity="0.42"/>
  <rect x="392" y="367" width="86" height="6" fill="#67e8f9" opacity="0.35"/>
  <rect x="500" y="363" width="92" height="7" fill="#f472b6" opacity="0.38"/>
  <ellipse cx="400" cy="322" rx="26" ry="40" fill="#030214" opacity="0.98"/>
  <ellipse cx="400" cy="274" rx="17" ry="20" fill="#030214" opacity="0.98"/>
  <rect x="0" y="0" width="5" height="450" fill="#38bdf8" opacity="0.6"/>
  <rect x="795" y="0" width="5" height="450" fill="#f0abfc" opacity="0.5"/>
  <rect x="0" y="368" width="800" height="82" fill="#06050f" opacity="0.9"/>
  <text x="400" y="408" font-family="Arial,sans-serif" font-size="30" fill="#f0abfc" text-anchor="middle" font-weight="bold" filter="url(#glow)">Neon District</text>
  <text x="400" y="433" font-family="Arial,sans-serif" font-size="13" fill="#c084fc" text-anchor="middle" letter-spacing="4">CYBERPUNK NOIR</text>
</svg>"""

session = r"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 450">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" stop-color="#7f1d1d"/>
      <stop offset="100%" stop-color="#991b1b"/>
    </linearGradient>
    <radialGradient id="lamp" cx="50%" cy="28%" r="40%">
      <stop offset="0%" stop-color="#fef08a" stop-opacity="0.7"/>
      <stop offset="100%" stop-color="#7f1d1d" stop-opacity="0"/>
    </radialGradient>
    <filter id="gf"><feGaussianBlur stdDeviation="5" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
    <filter id="blur"><feGaussianBlur stdDeviation="6"/></filter>
  </defs>
  <rect width="800" height="450" fill="url(#bg)"/>
  <rect width="800" height="450" fill="url(#lamp)"/>
  <polygon points="368,86 315,292 485,292 432,86" fill="#fef08a" opacity="0.11"/>
  <ellipse cx="400" cy="72" rx="65" ry="28" fill="#fef08a" opacity="0.26" filter="url(#blur)"/>
  <rect x="384" y="70" width="32" height="16" fill="#ca8a04" rx="4"/>
  <rect x="394" y="42" width="10" height="32" fill="#a16207"/>
  <ellipse cx="400" cy="80" rx="36" ry="13" fill="#f5d16a" opacity="0.85"/>
  <rect x="235" y="266" width="330" height="24" fill="#450a0a" rx="4"/>
  <rect x="250" y="290" width="16" height="125" fill="#3b0808"/>
  <rect x="534" y="290" width="16" height="125" fill="#3b0808"/>
  <rect x="272" y="246" width="84" height="22" fill="#fef3c7" opacity="0.42" rx="2"/>
  <rect x="372" y="252" width="68" height="17" fill="#fef3c7" opacity="0.35" rx="2"/>
  <ellipse cx="448" cy="256" rx="30" ry="11" fill="#dc2626" opacity="0.6" filter="url(#blur)"/>
  <rect x="188" y="252" width="88" height="76" fill="#2d0a0a" rx="8"/>
  <rect x="180" y="244" width="104" height="22" fill="#2d0a0a" rx="6"/>
  <rect x="180" y="244" width="17" height="84" fill="#1f0606" rx="4"/>
  <rect x="263" y="244" width="17" height="84" fill="#1f0606" rx="4"/>
  <rect x="524" y="222" width="82" height="92" fill="#1a0808" rx="8"/>
  <rect x="516" y="308" width="98" height="15" fill="#1a0808" rx="4"/>
  <rect x="100" y="88" width="118" height="160" fill="#1c3549" rx="4"/>
  <line x1="100" y1="108" x2="218" y2="108" stroke="#152638" stroke-width="5"/>
  <line x1="100" y1="128" x2="218" y2="128" stroke="#152638" stroke-width="5"/>
  <line x1="100" y1="148" x2="218" y2="148" stroke="#152638" stroke-width="5"/>
  <line x1="100" y1="168" x2="218" y2="168" stroke="#152638" stroke-width="5"/>
  <line x1="100" y1="188" x2="218" y2="188" stroke="#152638" stroke-width="5"/>
  <line x1="100" y1="208" x2="218" y2="208" stroke="#152638" stroke-width="5"/>
  <line x1="100" y1="228" x2="218" y2="228" stroke="#152638" stroke-width="5"/>
  <rect x="0" y="0" width="7" height="450" fill="#dc2626" opacity="0.7"/>
  <rect x="793" y="0" width="7" height="450" fill="#dc2626" opacity="0.5"/>
  <rect x="0" y="368" width="800" height="82" fill="#2d0707" opacity="0.88"/>
  <text x="400" y="408" font-family="Georgia,serif" font-size="30" fill="#fef2f2" text-anchor="middle" font-weight="bold">The Last Session</text>
  <text x="400" y="433" font-family="Arial,sans-serif" font-size="13" fill="#fca5a5" text-anchor="middle" letter-spacing="4">PSYCHOLOGICAL THRILLER</text>
</svg>"""

files = {
    'iu_murder_mystery': iu,
    'jennie_mini': jennie,
    'blackout_manor': blackout,
    'neon_district': neon,
    'the_last_session': session,
}

for name, content in files.items():
    path = os.path.join(base, f'{name}.svg')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f'wrote {name}.svg')

print('all done')
