#!/usr/bin/env python3
"""
Aircraft telemetry analytics and lightweight HTML visualization helpers.
"""
from dataclasses import dataclass
from html import escape
from typing import Dict, List

MAX_ALTITUDE_FT = 45_000
MAX_SPEED_KTS = 900


@dataclass(frozen=True)
class AircraftSnapshot:
    altitude_ft: float
    speed_kts: float
    heading_deg: float
    stealth_enabled: bool


def normalize_heading(heading_deg: float) -> float:
    normalized = heading_deg % 360
    return round(normalized, 1)


def heading_sector(heading_deg: float) -> str:
    sectors = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
    return sectors[int(((heading_deg + 22.5) % 360) // 45)]


def altitude_band(altitude_ft: float) -> str:
    if altitude_ft < 1_000:
        return "nap-of-earth"
    if altitude_ft < 10_000:
        return "low altitude"
    if altitude_ft < 30_000:
        return "mid altitude"
    return "high altitude"


def speed_band(speed_kts: float) -> str:
    if speed_kts < 200:
        return "loiter"
    if speed_kts < 450:
        return "transit"
    if speed_kts < 700:
        return "dash"
    return "extreme"


def energy_state(altitude_ft: float, speed_kts: float) -> str:
    if altitude_ft > 30_000 and speed_kts >= 450:
        return "high-energy intercept profile"
    if altitude_ft < 1_000 and speed_kts >= 350:
        return "terrain-following strike profile"
    if speed_kts < 180:
        return "low-energy endurance profile"
    return "balanced mission profile"


def build_aircraft_analysis(snapshot: AircraftSnapshot) -> Dict[str, object]:
    normalized_heading = normalize_heading(snapshot.heading_deg)
    altitude_label = altitude_band(snapshot.altitude_ft)
    speed_label = speed_band(snapshot.speed_kts)
    profile = energy_state(snapshot.altitude_ft, snapshot.speed_kts)

    security_flags: List[str] = []
    if not snapshot.stealth_enabled:
        security_flags.append("Stealth disabled increases radar exposure.")
    if snapshot.altitude_ft < 500 and snapshot.speed_kts > 350:
        security_flags.append("Low-altitude/high-speed ingress compresses reaction time.")
    if snapshot.altitude_ft > 40_000 and snapshot.speed_kts < 180:
        security_flags.append("Thin-air low-speed flight risks rapid energy bleed.")
    if snapshot.speed_kts >= 700:
        security_flags.append("Extreme speed may amplify thermal and structural signatures.")
    if snapshot.stealth_enabled and snapshot.altitude_ft > 35_000:
        security_flags.append("High-altitude stealth transit can still be seen by long-range sensors.")

    if snapshot.stealth_enabled and len(security_flags) <= 1:
        exposure = "low"
    elif len(security_flags) >= 3:
        exposure = "high"
    else:
        exposure = "medium"

    recommendations = []
    if exposure == "high":
        recommendations.append("Reduce signature pressure before entering contested airspace.")
    if altitude_label == "nap-of-earth":
        recommendations.append("Maintain terrain-clearance cross-checks for low-level operations.")
    if speed_label == "extreme":
        recommendations.append("Confirm thermal management and structural margins.")
    if not recommendations:
        recommendations.append("Current profile is stable for routine monitoring.")

    return {
        "basic": {
            "altitude_ft": round(snapshot.altitude_ft, 1),
            "speed_kts": round(snapshot.speed_kts, 1),
            "heading_deg": normalized_heading,
            "heading_sector": heading_sector(normalized_heading),
            "stealth_enabled": snapshot.stealth_enabled,
        },
        "advanced": {
            "altitude_band": altitude_label,
            "speed_band": speed_label,
            "energy_state": profile,
            "turn_axis": "eastbound" if 0 <= normalized_heading < 180 else "westbound",
        },
        "security": {
            "exposure_level": exposure,
            "flags": security_flags,
            "recommendations": recommendations,
        },
    }


def clamped_ratio(value: float, maximum: float) -> float:
    return min(max(value, 0), maximum) / maximum


def render_aircraft_visualization(snapshot: AircraftSnapshot) -> str:
    analysis = build_aircraft_analysis(snapshot)
    altitude_ratio = clamped_ratio(snapshot.altitude_ft, MAX_ALTITUDE_FT)
    speed_ratio = clamped_ratio(snapshot.speed_kts, MAX_SPEED_KTS)
    heading_deg = f'{analysis["basic"]["heading_deg"]:.1f}'
    stealth_text = "ENABLED" if snapshot.stealth_enabled else "DISABLED"
    stealth_class = "on" if snapshot.stealth_enabled else "off"
    security_flags = analysis["security"]["flags"] or ["No immediate security advisories."]
    recommendations = analysis["security"]["recommendations"]

    flag_items = "".join(f"<li>{escape(item)}</li>" for item in security_flags)
    recommendation_items = "".join(f"<li>{escape(item)}</li>" for item in recommendations)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Aircraft Visualization Modules</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #08111f;
      --panel: #101b2d;
      --panel-border: #223652;
      --accent: #43b3ff;
      --accent-2: #6df7c1;
      --warn: #ffc857;
      --danger: #ff6b6b;
      --text: #e8f1ff;
      --muted: #a7b4c7;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Inter, Arial, sans-serif;
      background: radial-gradient(circle at top, #13233d, var(--bg) 60%);
      color: var(--text);
    }}
    .page {{
      max-width: 1180px;
      margin: 0 auto;
      padding: 24px;
    }}
    .grid {{
      display: grid;
      gap: 16px;
    }}
    .controls, .panel {{
      background: rgba(16, 27, 45, 0.92);
      border: 1px solid var(--panel-border);
      border-radius: 18px;
      box-shadow: 0 20px 60px rgba(0, 0, 0, 0.28);
    }}
    .controls {{
      padding: 18px;
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 12px;
      align-items: end;
    }}
    .controls label {{
      display: block;
      font-size: 0.9rem;
      color: var(--muted);
      margin-bottom: 6px;
    }}
    .controls input {{
      width: 100%;
      border-radius: 10px;
      border: 1px solid #375170;
      padding: 10px 12px;
      background: #091220;
      color: var(--text);
    }}
    .controls button {{
      height: 42px;
      border: 0;
      border-radius: 10px;
      background: linear-gradient(135deg, var(--accent), #2a70ff);
      color: white;
      font-weight: 700;
      cursor: pointer;
    }}
    .cards {{
      grid-template-columns: repeat(4, minmax(0, 1fr));
    }}
    .panel {{
      padding: 18px;
      overflow: hidden;
    }}
    .eyebrow {{
      color: var(--muted);
      font-size: 0.78rem;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }}
    .metric {{
      font-size: 2rem;
      font-weight: 800;
      margin-top: 6px;
    }}
    .subtle {{
      color: var(--muted);
      margin-top: 6px;
    }}
    .altitude-bar {{
      height: 160px;
      width: 24px;
      border-radius: 999px;
      background: #07101d;
      border: 1px solid #2a3d59;
      position: relative;
      margin-top: 16px;
      overflow: hidden;
    }}
    .altitude-bar span {{
      position: absolute;
      inset: auto 0 0 0;
      height: {altitude_ratio * 100:.1f}%;
      background: linear-gradient(180deg, var(--accent), var(--accent-2));
    }}
    .speed-track {{
      margin-top: 18px;
      height: 14px;
      background: #07101d;
      border-radius: 999px;
      overflow: hidden;
      border: 1px solid #2a3d59;
    }}
    .speed-track span {{
      display: block;
      height: 100%;
      width: {speed_ratio * 100:.1f}%;
      background: linear-gradient(90deg, var(--accent), var(--warn));
    }}
    .compass {{
      width: 160px;
      height: 160px;
      border-radius: 50%;
      border: 1px solid #375170;
      margin-top: 14px;
      position: relative;
      display: grid;
      place-items: center;
      background: radial-gradient(circle, rgba(67,179,255,0.08), transparent 70%);
    }}
    .compass::before {{
      content: "N";
      position: absolute;
      top: 10px;
      color: var(--muted);
    }}
    .needle {{
      width: 6px;
      height: 58px;
      background: linear-gradient(180deg, var(--danger), white);
      border-radius: 999px;
      transform-origin: center 48px;
      transform: rotate({heading_deg}deg);
      box-shadow: 0 0 16px rgba(255, 107, 107, 0.6);
    }}
    .stealth {{
      margin-top: 18px;
      padding: 18px;
      border-radius: 14px;
      text-align: center;
      font-weight: 800;
      letter-spacing: 0.08em;
    }}
    .stealth.on {{
      background: rgba(109, 247, 193, 0.12);
      border: 1px solid rgba(109, 247, 193, 0.4);
      color: var(--accent-2);
    }}
    .stealth.off {{
      background: rgba(255, 107, 107, 0.12);
      border: 1px solid rgba(255, 107, 107, 0.4);
      color: #ffb3b3;
    }}
    .split {{
      grid-template-columns: 1.1fr 0.9fr;
    }}
    .list {{
      margin: 14px 0 0;
      padding-left: 18px;
      color: var(--text);
    }}
    .pill {{
      display: inline-flex;
      margin-top: 10px;
      padding: 6px 10px;
      border-radius: 999px;
      background: rgba(67, 179, 255, 0.12);
      color: var(--accent);
      font-size: 0.9rem;
      font-weight: 700;
    }}
    .security-low {{ color: var(--accent-2); }}
    .security-medium {{ color: var(--warn); }}
    .security-high {{ color: var(--danger); }}
    @media (max-width: 960px) {{
      .controls, .cards, .split {{
        grid-template-columns: 1fr;
      }}
      .compass {{
        margin-inline: auto;
      }}
    }}
  </style>
</head>
<body>
  <div class="page grid">
    <section class="controls">
      <form method="get" style="display: contents;">
        <div>
          <label for="altitude">Altitude (ft)</label>
          <input id="altitude" name="altitude" type="number" min="0" value="{snapshot.altitude_ft:.1f}">
        </div>
        <div>
          <label for="speed">Speed (kts)</label>
          <input id="speed" name="speed" type="number" min="0" value="{snapshot.speed_kts:.1f}">
        </div>
        <div>
          <label for="heading">Heading (deg)</label>
          <input id="heading" name="heading" type="number" value="{snapshot.heading_deg:.1f}">
        </div>
        <div>
          <label for="stealth">Stealth Enabled</label>
          <input id="stealth" name="stealth" type="checkbox" value="true" {"checked" if snapshot.stealth_enabled else ""}>
        </div>
        <button type="submit">Update Modules</button>
      </form>
    </section>

    <section class="grid cards">
      <article class="panel">
        <div class="eyebrow">Altitude Module</div>
        <div class="metric">{analysis["basic"]["altitude_ft"]:.0f} ft</div>
        <div class="subtle">{escape(analysis["advanced"]["altitude_band"])}</div>
        <div class="altitude-bar"><span></span></div>
      </article>
      <article class="panel">
        <div class="eyebrow">Speed Module</div>
        <div class="metric">{analysis["basic"]["speed_kts"]:.0f} kts</div>
        <div class="subtle">{escape(analysis["advanced"]["speed_band"])}</div>
        <div class="speed-track"><span></span></div>
      </article>
      <article class="panel">
        <div class="eyebrow">Heading Module</div>
        <div class="metric">{analysis["basic"]["heading_deg"]:.1f}°</div>
        <div class="subtle">{escape(analysis["basic"]["heading_sector"])} / {escape(analysis["advanced"]["turn_axis"])}</div>
        <div class="compass"><div class="needle"></div></div>
      </article>
      <article class="panel">
        <div class="eyebrow">Stealth Module</div>
        <div class="metric">{stealth_text}</div>
        <div class="subtle">Security posture visualization</div>
        <div class="stealth {stealth_class}">{stealth_text}</div>
      </article>
    </section>

    <section class="grid split">
      <article class="panel">
        <div class="eyebrow">Advanced Analytics</div>
        <div class="metric">{escape(analysis["advanced"]["energy_state"])}</div>
        <div class="pill">Basic + advanced mission interpretation</div>
        <ul class="list">
          <li>Altitude band: {escape(analysis["advanced"]["altitude_band"])}</li>
          <li>Speed band: {escape(analysis["advanced"]["speed_band"])}</li>
          <li>Heading sector: {escape(analysis["basic"]["heading_sector"])}</li>
          <li>Turn axis: {escape(analysis["advanced"]["turn_axis"])}</li>
        </ul>
      </article>
      <article class="panel">
        <div class="eyebrow">Security-Focused View</div>
        <div class="metric security-{escape(analysis["security"]["exposure_level"])}">{escape(analysis["security"]["exposure_level"]).upper()} EXPOSURE</div>
        <div class="subtle">Threat-informed telemetry review</div>
        <ul class="list">{flag_items}</ul>
        <div class="pill">Recommended actions</div>
        <ul class="list">{recommendation_items}</ul>
      </article>
    </section>
  </div>
</body>
</html>
"""
