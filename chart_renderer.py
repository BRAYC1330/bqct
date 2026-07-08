import json
import re
import logging
import subprocess
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

CANVAS_W = 512
CANVAS_H = 512
CHART_LEFT = 60
CHART_RIGHT = 480
CHART_TOP = 80
CHART_BOTTOM = 440
CHART_W = CHART_RIGHT - CHART_LEFT
CHART_H = CHART_BOTTOM - CHART_TOP
GRID_SIZE = 12
CELL_W = CHART_W / GRID_SIZE
CELL_H = CHART_H / GRID_SIZE

def parse_candles_json(raw: str) -> Optional[List[Dict]]:
    try:
        match = re.search(r'\[[\s\S]*\]', raw)
        if not match:
            return None
        candles = json.loads(match.group(0))
        if not isinstance(candles, list) or len(candles) != 12:
            return None
        for c in candles:
            if not all(k in c for k in ('o', 'h', 'l', 'c')):
                return None
            for k in ('o', 'h', 'l', 'c'):
                v = float(c[k])
                if v < 0 or v > 12:
                    return None
                c[k] = v
        return candles
    except Exception as e:
        logger.warning(f"[chart] JSON parse failed: {e}")
        return None

def validate_and_fix_candles(candles: List[Dict]) -> List[Dict]:
    for i in range(len(candles)):
        c = candles[i]
        c['h'] = max(c['h'], c['o'], c['c'])
        c['l'] = min(c['l'], c['o'], c['c'])
        if i > 0:
            c['o'] = candles[i-1]['c']
    return candles

def value_to_y(v: float) -> int:
    return int(CHART_BOTTOM - (v / GRID_SIZE) * CHART_H)

def render_chart_svg(candles: List[Dict], title: str = "AI SENTIMENT INDEX", subtitle: str = "") -> str:
    start_val = candles[0]['o']
    peak = max(c['h'] for c in candles)
    drop = min(c['l'] for c in candles)
    now_val = candles[-1]['c']
    
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" style="stop-color:#050810"/>
      <stop offset="100%" style="stop-color:#0a1020"/>
    </linearGradient>
  </defs>
  <rect width="512" height="512" fill="url(#bg)"/>
  <text x="256" y="32" text-anchor="middle" fill="#ffffff" font-family="Arial, sans-serif" font-size="18" font-weight="bold" letter-spacing="2">{title}</text>
  <text x="256" y="50" text-anchor="middle" fill="#8892a8" font-family="Arial, sans-serif" font-size="10" letter-spacing="1">{subtitle}</text>
  <g stroke="#1a2030" stroke-width="0.3">'''
    
    for i in range(GRID_SIZE + 1):
        x = CHART_LEFT + i * CELL_W
        svg += f'\n    <line x1="{x:.1f}" y1="{CHART_TOP}" x2="{x:.1f}" y2="{CHART_BOTTOM}"/>'
    for i in range(GRID_SIZE + 1):
        y = CHART_TOP + i * CELL_H
        svg += f'\n    <line x1="{CHART_LEFT}" y1="{y:.1f}" x2="{CHART_RIGHT}" y2="{y:.1f}"/>'
    
    svg += '\n  </g>\n  <g font-family="Arial, sans-serif" font-size="11" font-weight="bold" fill="#c8d0e0">'
    for v in [12, 9, 6, 3, 0]:
        y = value_to_y(v) + 4
        svg += f'\n    <text x="52" y="{y}" text-anchor="end">{v}</text>'
    svg += '\n  </g>\n  <g font-family="Arial, sans-serif" font-size="11" font-weight="bold" fill="#c8d0e0">'
    for i in range(1, 13):
        x = CHART_LEFT + (i - 0.5) * CELL_W
        svg += f'\n    <text x="{x:.1f}" y="{CHART_BOTTOM + 18}" text-anchor="middle">{i}</text>'
    svg += '\n  </g>'
    
    for i, c in enumerate(candles):
        cx = CHART_LEFT + (i + 0.5) * CELL_W
        is_bull = c['c'] >= c['o']
        color = "#00ff88" if is_bull else "#ff3366"
        body_top = value_to_y(max(c['o'], c['c']))
        body_bot = value_to_y(min(c['o'], c['c']))
        body_h = max(body_bot - body_top, 2)
        wick_top = value_to_y(c['h'])
        wick_bot = value_to_y(c['l'])
        bar_w = CELL_W * 0.6
        x1 = cx - bar_w / 2
        
        svg += f'\n  <g>'
        svg += f'\n    <line x1="{cx:.1f}" y1="{wick_top}" x2="{cx:.1f}" y2="{wick_bot}" stroke="{color}" stroke-width="2"/>'
        svg += f'\n    <rect x="{x1:.1f}" y="{body_top}" width="{bar_w:.1f}" height="{body_h}" fill="{color}" stroke="{color}" stroke-width="0.5"/>'
        svg += f'\n  </g>'
    
    svg += f'\n  <g>'
    svg += f'\n    <rect x="380" y="480" width="10" height="10" fill="#00ff88"/>'
    svg += f'\n    <text x="395" y="489" fill="#00ff88" font-family="Arial, sans-serif" font-size="11" font-weight="bold">BULLISH</text>'
    svg += f'\n    <rect x="440" y="480" width="10" height="10" fill="#ff3366"/>'
    svg += f'\n    <text x="455" y="489" fill="#ff3366" font-family="Arial, sans-serif" font-size="11" font-weight="bold">BEARISH</text>'
    svg += f'\n  </g>'
    svg += f'\n  <g>'
    svg += f'\n    <circle cx="78" cy="490" r="4" fill="#00ff88"/>'
    svg += f'\n    <text x="88" y="494" fill="#c8d0e0" font-family="Arial, sans-serif" font-size="10" font-weight="bold">START: {start_val:.1f}</text>'
    svg += f'\n    <circle cx="175" cy="490" r="4" fill="#00ff88"/>'
    svg += f'\n    <text x="185" y="494" fill="#c8d0e0" font-family="Arial, sans-serif" font-size="10" font-weight="bold">PEAK: {peak:.1f}</text>'
    svg += f'\n    <circle cx="270" cy="490" r="4" fill="#ff3366"/>'
    svg += f'\n    <text x="280" y="494" fill="#c8d0e0" font-family="Arial, sans-serif" font-size="10" font-weight="bold">DROP: {drop:.1f}</text>'
    svg += f'\n    <circle cx="365" cy="490" r="4" fill="#00ff88"/>'
    svg += f'\n    <text x="375" y="494" fill="#c8d0e0" font-family="Arial, sans-serif" font-size="10" font-weight="bold">NOW: {now_val:.1f}</text>'
    svg += f'\n  </g>'
    svg += '\n</svg>'
    
    return svg

def svg_to_png(svg_str: str, output_path: str = "chart_output.png") -> bytes:
    try:
        result = subprocess.run(
            ["rsvg-convert", "-w", "512", "-h", "512", "-o", output_path],
            input=svg_str.encode("utf-8"),
            capture_output=True
        )
        if result.returncode != 0:
            logger.error(f"[chart] rsvg-convert failed: {result.stderr.decode()}")
            return None
        with open(output_path, "rb") as f:
            return f.read()
    except Exception as e:
        logger.error(f"[chart] PNG conversion failed: {e}")
        return None
