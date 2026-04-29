"""
HealthGuardian - 科技感健康仪表盘生成器
生成包含趋势图、用药依从率、就医待办的暗色主题 HTML 仪表盘
使用 Chart.js 进行数据可视化，含粒子背景和数字动画
"""

import json
import os
import sqlite3
from datetime import datetime, timedelta


def get_dashboard_data(db_path: str = 'health_log.db') -> dict:
    """从数据库获取仪表盘所需的全部数据"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    data = {
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'metrics': {
            'dates': [],
            'systolic_bp': [],
            'diastolic_bp': [],
            'heart_rate': [],
            'fasting_glucose': [],
            'sleep_hours': [],
            'steps': [],
        },
        'medications': [],
        'follow_ups': [],
        'health_logs': [],
        'stats': {
            'total_metrics': 0,
            'total_logs': 0,
            'active_meds': 0,
            'pending_followups': 0,
        },
        'alerts': {
            'overdue': [],
            'low_stock': [],
            'expired': [],
            'missed_meds': [],
        },
    }

    # 1. 指标趋势（最近30天）
    c = conn.cursor()
    c.execute("""
        SELECT date, systolic_bp, diastolic_bp, heart_rate,
               fasting_glucose, sleep_hours, steps
        FROM daily_metrics
        WHERE date >= date('now', '-30 days')
        ORDER BY date ASC
    """)
    for row in c.fetchall():
        d = row['date'][5:]  # MM-DD 格式
        data['metrics']['dates'].append(d)
        data['metrics']['systolic_bp'].append(row['systolic_bp'])
        data['metrics']['diastolic_bp'].append(row['diastolic_bp'])
        data['metrics']['heart_rate'].append(row['heart_rate'])
        data['metrics']['fasting_glucose'].append(row['fasting_glucose'])
        data['metrics']['sleep_hours'].append(row['sleep_hours'])
        data['metrics']['steps'].append(row['steps'])
    data['stats']['total_metrics'] = len(data['metrics']['dates'])

    # 2. 活跃药品
    c.execute("""
        SELECT id, name, dosage, frequency, remaining_quantity,
               expiry_date, low_stock_threshold
        FROM medications
        WHERE is_active = 1
        ORDER BY expiry_date ASC
    """)
    for row in c.fetchall():
        data['medications'].append(dict(row))
    data['stats']['active_meds'] = len(data['medications'])

    # 3. 就医待办
    c.execute("""
        SELECT * FROM follow_up_actions
        WHERE status != '已完成' AND status != '已取消'
        ORDER BY priority ASC, due_date ASC
    """)
    for row in c.fetchall():
        data['follow_ups'].append(dict(row))
    data['stats']['pending_followups'] = len(data['follow_ups'])

    # 4. 过期预警
    c.execute("""
        SELECT title, due_date, priority FROM follow_up_actions
        WHERE status NOT IN ('已完成', '已取消')
        AND due_date IS NOT NULL AND due_date < date('now','localtime')
        ORDER BY priority ASC
    """)
    data['alerts']['overdue'] = [dict(r) for r in c.fetchall()]

    # 5. 药品余量预警
    c.execute("""
        SELECT name, remaining_quantity, low_stock_threshold, frequency
        FROM medications
        WHERE is_active = 1 AND remaining_quantity > 0
        AND remaining_quantity <= low_stock_threshold
    """)
    data['alerts']['low_stock'] = [dict(r) for r in c.fetchall()]

    # 6. 过期药品
    c.execute("""
        SELECT name, expiry_date, remaining_quantity FROM medications
        WHERE is_active = 1 AND expiry_date < date('now','localtime')
    """)
    data['alerts']['expired'] = [dict(r) for r in c.fetchall()]

    # 7. 最近健康日志
    c.execute("""
        SELECT date, category, title, severity FROM health_logs
        ORDER BY date DESC, id DESC LIMIT 10
    """)
    for row in c.fetchall():
        data['health_logs'].append(dict(row))
    data['stats']['total_logs'] = len(data['health_logs'])

    # 8. 服药依从性（每个活跃药品，使用 DatabaseManager 的精确计算）
    try:
        import sys
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from db_manager import DatabaseManager
        tmp_db = DatabaseManager(db_path)
        for med in data['medications']:
            adherence = tmp_db.get_adherence_rate(med['id'], days=30)
            if adherence:
                med['adherence'] = adherence['adherence_rate']
                med['days_taken'] = adherence['actual_doses']
            else:
                med['adherence'] = 0
                med['days_taken'] = 0
        tmp_db.close()
    except Exception:
        for med in data['medications']:
            med['adherence'] = 0
            med['days_taken'] = 0

    conn.close()
    return data


def generate_html(data: dict) -> str:
    """生成科技感 HTML 仪表盘"""
    # 准备 Chart.js 数据（过滤掉 None 值）
    def clean_series(dates, values):
        result_dates, result_values = [], []
        for d, v in zip(dates, values):
            if v is not None:
                result_dates.append(d)
                result_values.append(v)
        return json.dumps(result_dates), json.dumps(result_values)

    bp_dates, bp_sys = clean_series(data['metrics']['dates'], data['metrics']['systolic_bp'])
    _, bp_dia = clean_series(data['metrics']['dates'], data['metrics']['diastolic_bp'])
    hr_dates, hr_vals = clean_series(data['metrics']['dates'], data['metrics']['heart_rate'])
    glu_dates, glu_vals = clean_series(data['metrics']['dates'], data['metrics']['fasting_glucose'])

    # 就医待办 HTML
    followups_html = ''
    for f in data['follow_ups'][:8]:
        priority_color = {'高': '#ff4757', '中': '#ffa502', '低': '#2ed573'}
        priority_glow = {'高': '0 0 8px rgba(255,71,87,0.6)', '中': '0 0 8px rgba(255,165,2,0.6)', '低': '0 0 8px rgba(46,213,115,0.6)'}
        color = priority_color.get(f['priority'], '#888780')
        glow = priority_glow.get(f['priority'], 'none')
        due = f.get('due_date', '') or '无截止日期'
        followups_html += f'''
        <div style="display:flex;align-items:center;gap:10px;padding:8px 12px;margin-bottom:6px;border-radius:8px;background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.06);transition:all 0.3s;">
            <span style="width:8px;height:8px;border-radius:50%;background:{color};flex-shrink:0;box-shadow:{glow};"></span>
            <span style="flex:1;font-size:13px;color:#e8e8e8;">{f['title']}</span>
            <span style="font-size:11px;color:rgba(255,255,255,0.4);">{due}</span>
        </div>'''

    # 预警 HTML
    alerts_html = ''
    for a in data['alerts']['overdue']:
        alerts_html += f'''<div style="padding:8px 12px;margin-bottom:6px;border-radius:8px;background:rgba(255,71,87,0.08);border-left:3px solid #ff4757;font-size:12px;color:#ff6b7a;">
            <span style="opacity:0.7;">[过期]</span> {a["title"]} <span style="opacity:0.5;">({a["due_date"]})</span></div>'''
    for a in data['alerts']['low_stock']:
        alerts_html += f'''<div style="padding:8px 12px;margin-bottom:6px;border-radius:8px;background:rgba(255,165,2,0.08);border-left:3px solid #ffa502;font-size:12px;color:#ffc048;">
            <span style="opacity:0.7;">[余量低]</span> {a["name"]} 剩余{a["remaining_quantity"]}片</div>'''
    for a in data['alerts']['expired']:
        alerts_html += f'''<div style="padding:8px 12px;margin-bottom:6px;border-radius:8px;background:rgba(255,71,87,0.08);border-left:3px solid #ff4757;font-size:12px;color:#ff6b7a;">
            <span style="opacity:0.7;">[已过期]</span> {a["name"]} ({a["expiry_date"]})</div>'''
    if not alerts_html:
        alerts_html = '''<div style="padding:12px;text-align:center;font-size:13px;color:rgba(46,213,115,0.7);border:1px dashed rgba(46,213,115,0.2);border-radius:8px;">
            &#10003; 系统运行正常，暂无预警</div>'''

    # 健康日志 HTML
    logs_html = ''
    for l in data['health_logs'][:5]:
        severity_icon = {'轻': '○', '中': '◑', '重': '●'}
        severity_color = {'轻': '#2ed573', '中': '#ffa502', '重': '#ff4757'}
        icon = severity_icon.get(l.get('severity', ''), '○')
        scolor = severity_color.get(l.get('severity', ''), '#888')
        logs_html += f'''
        <div style="padding:6px 0;font-size:12px;color:rgba(255,255,255,0.7);border-bottom:1px solid rgba(255,255,255,0.04);">
            <span style="color:rgba(255,255,255,0.3);margin-right:8px;">{l["date"]}</span>
            <span style="color:{scolor};margin-right:4px;">{icon}</span>
            <span style="color:rgba(255,255,255,0.4);margin-right:4px;">[{l["category"]}]</span>
            {l["title"]}
        </div>'''
    if not logs_html:
        logs_html = '<div style="padding:12px;text-align:center;font-size:12px;color:rgba(255,255,255,0.3);">暂无健康日志</div>'

    # 依从性卡片 HTML
    med_cards_html = ''
    for m in data['medications']:
        if m['adherence'] >= 80:
            bar_color = '#2ed573'
            bar_gradient = 'linear-gradient(90deg, #2ed573, #7bed9f)'
            glow = '0 0 12px rgba(46,213,115,0.4)'
        elif m['adherence'] >= 50:
            bar_color = '#ffa502'
            bar_gradient = 'linear-gradient(90deg, #ffa502, #ffc048)'
            glow = '0 0 12px rgba(255,165,2,0.3)'
        else:
            bar_color = '#ff4757'
            bar_gradient = 'linear-gradient(90deg, #ff4757, #ff6b7a)'
            glow = '0 0 12px rgba(255,71,87,0.3)'
        med_cards_html += f'''
        <div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.06);border-radius:10px;padding:12px;transition:all 0.3s;">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
                <span style="font-size:13px;color:#e8e8e8;">{m["name"]}</span>
                <span style="font-size:14px;font-weight:600;color:{bar_color};text-shadow:0 0 8px {bar_color};">{m["adherence"]}%</span>
            </div>
            <div style="height:6px;background:rgba(255,255,255,0.06);border-radius:3px;overflow:hidden;">
                <div class="progress-bar" style="height:6px;background:{bar_gradient};border-radius:3px;width:{min(m["adherence"],100)}%;box-shadow:{glow};"></div>
            </div>
            <div style="display:flex;justify-content:space-between;margin-top:6px;font-size:11px;color:rgba(255,255,255,0.35);">
                <span>剩余 {m["remaining_quantity"]}片</span>
                <span>{m["frequency"]}</span>
            </div>
        </div>'''

    # 计算预警总数
    total_alerts = len(data['alerts']['overdue']) + len(data['alerts']['low_stock']) + len(data['alerts']['expired'])
    alerts_color = '#ff4757' if total_alerts > 0 else '#2ed573'
    alerts_glow = '0 0 20px rgba(255,71,87,0.5)' if total_alerts > 0 else '0 0 20px rgba(46,213,115,0.5)'

    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>HealthGuardian · 健康仪表盘</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<style>
    @import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@400;500;600;700&display=swap');

    :root {{
        --bg-primary: #0a0e17;
        --bg-secondary: #111827;
        --bg-card: rgba(17, 24, 39, 0.8);
        --border-glow: rgba(56, 189, 248, 0.15);
        --accent-blue: #38bdf8;
        --accent-cyan: #22d3ee;
        --accent-green: #2ed573;
        --accent-red: #ff4757;
        --accent-orange: #ffa502;
        --text-primary: #f0f0f5;
        --text-secondary: rgba(240, 240, 245, 0.6);
        --text-dim: rgba(240, 240, 245, 0.3);
    }}

    * {{ margin: 0; padding: 0; box-sizing: border-box; }}

    body {{
        font-family: 'Rajdhani', -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
        background: var(--bg-primary);
        color: var(--text-primary);
        line-height: 1.6;
        min-height: 100vh;
        overflow-x: hidden;
    }}

    /* Grid background */
    body::before {{
        content: '';
        position: fixed;
        top: 0; left: 0; right: 0; bottom: 0;
        background-image:
            linear-gradient(rgba(56, 189, 248, 0.03) 1px, transparent 1px),
            linear-gradient(90deg, rgba(56, 189, 248, 0.03) 1px, transparent 1px);
        background-size: 40px 40px;
        pointer-events: none;
        z-index: 0;
    }}

    /* Scanline animation */
    body::after {{
        content: '';
        position: fixed;
        top: 0; left: 0; right: 0;
        height: 2px;
        background: linear-gradient(90deg, transparent, var(--accent-cyan), transparent);
        opacity: 0.3;
        animation: scanline 4s linear infinite;
        pointer-events: none;
        z-index: 100;
    }}

    @keyframes scanline {{
        0% {{ top: -2px; }}
        100% {{ top: 100vh; }}
    }}

    /* Particle canvas */
    #particles {{
        position: fixed;
        top: 0; left: 0;
        width: 100%; height: 100%;
        pointer-events: none;
        z-index: 0;
    }}

    .container {{
        position: relative;
        z-index: 1;
        max-width: 960px;
        margin: 0 auto;
        padding: 24px 20px 40px;
    }}

    /* Header */
    .header {{
        text-align: center;
        margin-bottom: 28px;
        padding: 20px 0;
    }}

    .header .logo {{
        display: inline-flex;
        align-items: center;
        gap: 12px;
        margin-bottom: 8px;
    }}

    .header .logo-icon {{
        width: 40px; height: 40px;
        border-radius: 10px;
        background: linear-gradient(135deg, var(--accent-blue), var(--accent-cyan));
        display: flex; align-items: center; justify-content: center;
        font-size: 20px;
        box-shadow: 0 0 24px rgba(56, 189, 248, 0.3);
        animation: pulse-glow 3s ease-in-out infinite;
    }}

    @keyframes pulse-glow {{
        0%, 100% {{ box-shadow: 0 0 24px rgba(56, 189, 248, 0.3); }}
        50% {{ box-shadow: 0 0 36px rgba(56, 189, 248, 0.5); }}
    }}

    .header h1 {{
        font-size: 26px;
        font-weight: 600;
        background: linear-gradient(135deg, #e0e7ff, var(--accent-cyan));
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        letter-spacing: 1px;
    }}

    .header .meta {{
        font-size: 12px;
        color: var(--text-dim);
        margin-top: 6px;
        letter-spacing: 2px;
        text-transform: uppercase;
    }}

    .header .meta::before,
    .header .meta::after {{
        content: '\\2014';
        margin: 0 8px;
        opacity: 0.4;
    }}

    /* Stat cards */
    .stats-row {{
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 12px;
        margin-bottom: 20px;
    }}

    .stat-card {{
        background: var(--bg-card);
        backdrop-filter: blur(10px);
        border-radius: 12px;
        padding: 16px 12px;
        text-align: center;
        border: 1px solid var(--border-glow);
        position: relative;
        overflow: hidden;
        transition: all 0.3s;
    }}

    .stat-card:hover {{
        border-color: rgba(56, 189, 248, 0.3);
        box-shadow: 0 0 20px rgba(56, 189, 248, 0.1);
        transform: translateY(-2px);
    }}

    .stat-card::before {{
        content: '';
        position: absolute;
        top: 0; left: 0; right: 0;
        height: 2px;
        background: linear-gradient(90deg, transparent, var(--accent-blue), transparent);
        opacity: 0.6;
    }}

    .stat-value {{
        font-size: 28px;
        font-weight: 700;
        color: var(--text-primary);
        font-family: 'Rajdhani', monospace;
    }}

    .stat-label {{
        font-size: 11px;
        color: var(--text-secondary);
        margin-top: 2px;
        letter-spacing: 1px;
    }}

    /* Card */
    .card {{
        background: var(--bg-card);
        backdrop-filter: blur(10px);
        border-radius: 14px;
        padding: 18px;
        margin-bottom: 16px;
        border: 1px solid var(--border-glow);
        position: relative;
        overflow: hidden;
        transition: all 0.3s;
        animation: cardFadeIn 0.5s ease-out forwards;
        opacity: 0;
    }}

    .card:hover {{
        border-color: rgba(56, 189, 248, 0.25);
        box-shadow: 0 4px 30px rgba(56, 189, 248, 0.06);
    }}

    .card-title {{
        font-size: 14px;
        font-weight: 500;
        color: var(--text-secondary);
        margin-bottom: 14px;
        display: flex;
        align-items: center;
        gap: 8px;
        letter-spacing: 1px;
        text-transform: uppercase;
    }}

    .card-title::before {{
        content: '';
        width: 3px; height: 14px;
        background: var(--accent-cyan);
        border-radius: 2px;
        box-shadow: 0 0 8px var(--accent-cyan);
    }}

    @keyframes cardFadeIn {{
        from {{ opacity: 0; transform: translateY(20px); }}
        to {{ opacity: 1; transform: translateY(0); }}
    }}

    .chart-container {{
        position: relative;
        height: 220px;
    }}

    .grid-2 {{
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 16px;
    }}

    .progress-bar {{
        transition: width 1.5s cubic-bezier(0.4, 0, 0.2, 1);
    }}

    .alert-section {{
        background: rgba(255, 255, 255, 0.02);
        border-radius: 10px;
        padding: 4px 0;
    }}

    /* Status bar */
    .status-bar {{
        text-align: center;
        margin-top: 24px;
        padding: 12px;
        font-size: 11px;
        color: var(--text-dim);
        letter-spacing: 2px;
        border-top: 1px solid rgba(56, 189, 248, 0.08);
    }}

    .status-dot {{
        display: inline-block;
        width: 6px; height: 6px;
        background: var(--accent-green);
        border-radius: 50%;
        margin-right: 6px;
        box-shadow: 0 0 8px var(--accent-green);
        animation: blink 2s ease-in-out infinite;
    }}

    @keyframes blink {{
        0%, 100% {{ opacity: 1; }}
        50% {{ opacity: 0.3; }}
    }}

    @media (max-width: 600px) {{
        .stats-row {{ grid-template-columns: repeat(2, 1fr); }}
        .grid-2 {{ grid-template-columns: 1fr; }}
        .header h1 {{ font-size: 20px; }}
    }}

    @media (prefers-reduced-motion: reduce) {{
        *, *::before, *::after {{
            animation-duration: 0.01ms !important;
            transition-duration: 0.01ms !important;
        }}
    }}
</style>
</head>
<body>
<canvas id="particles"></canvas>

<div class="container">
    <div class="header">
        <div class="logo">
            <div class="logo-icon">&#9829;</div>
            <h1>HealthGuardian</h1>
        </div>
        <div class="meta">{data['generated_at']} &middot; 最近30天</div>
    </div>

    <div class="stats-row">
        <div class="stat-card">
            <div class="stat-value" data-target="{data['stats']['total_metrics']}">0</div>
            <div class="stat-label">数据天数</div>
        </div>
        <div class="stat-card">
            <div class="stat-value" data-target="{data['stats']['active_meds']}">0</div>
            <div class="stat-label">活跃药品</div>
        </div>
        <div class="stat-card">
            <div class="stat-value" data-target="{len(data['alerts']['overdue'])}" style="color:{alerts_color};text-shadow:0 0 12px {alerts_color};">0</div>
            <div class="stat-label">过期待办</div>
        </div>
        <div class="stat-card">
            <div class="stat-value" data-target="{total_alerts}" style="color:{"#ff4757" if total_alerts > 0 else "#2ed573"};text-shadow:0 0 12px {"rgba(255,71,87,0.5)" if total_alerts > 0 else "rgba(46,213,115,0.5)"};">0</div>
            <div class="stat-label">预警信号</div>
        </div>
    </div>

    <div class="card">
        <div class="card-title">血压趋势 Blood Pressure</div>
        <div class="chart-container"><canvas id="bpChart" role="img" aria-label="血压趋势折线图"></canvas></div>
    </div>

    <div class="grid-2">
        <div class="card">
            <div class="card-title">心率 Heart Rate</div>
            <div class="chart-container"><canvas id="hrChart" role="img" aria-label="心率趋势折线图"></canvas></div>
        </div>
        <div class="card">
            <div class="card-title">空腹血糖 Glucose</div>
            <div class="chart-container"><canvas id="gluChart" role="img" aria-label="血糖趋势折线图"></canvas></div>
        </div>
    </div>

    <div class="grid-2">
        <div class="card">
            <div class="card-title">用药依从性 Adherence</div>
            <div style="display:grid;gap:8px;">{med_cards_html if med_cards_html else '<div style="font-size:13px;color:var(--text-dim);text-align:center;padding:20px;">暂无活跃药品</div>'}</div>
        </div>
        <div class="card">
            <div class="card-title">系统预警 Alerts</div>
            <div class="alert-section">{alerts_html}</div>
        </div>
    </div>

    <div class="grid-2">
        <div class="card">
            <div class="card-title">就医待办 Follow-up</div>
            {followups_html if followups_html else '<div style="font-size:13px;color:var(--text-dim);text-align:center;padding:20px;">暂无待办事项</div>'}
        </div>
        <div class="card">
            <div class="card-title">健康日志 Health Log</div>
            {logs_html}
        </div>
    </div>

    <div class="status-bar">
        <span class="status-dot"></span>
        HealthGuardian v2.0 &middot; Powered by WorkBuddy
    </div>
</div>

<script>
// === Particle background ===
(function() {{
    const canvas = document.getElementById('particles');
    const ctx = canvas.getContext('2d');
    let particles = [];
    const PARTICLE_COUNT = 50;

    function resize() {{
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;
    }}
    resize();
    window.addEventListener('resize', resize);

    class Particle {{
        constructor() {{ this.reset(); }}
        reset() {{
            this.x = Math.random() * canvas.width;
            this.y = Math.random() * canvas.height;
            this.vx = (Math.random() - 0.5) * 0.3;
            this.vy = (Math.random() - 0.5) * 0.3;
            this.radius = Math.random() * 1.5 + 0.5;
            this.opacity = Math.random() * 0.3 + 0.1;
        }}
        update() {{
            this.x += this.vx;
            this.y += this.vy;
            if (this.x < 0 || this.x > canvas.width) this.vx *= -1;
            if (this.y < 0 || this.y > canvas.height) this.vy *= -1;
        }}
        draw() {{
            ctx.beginPath();
            ctx.arc(this.x, this.y, this.radius, 0, Math.PI * 2);
            ctx.fillStyle = 'rgba(56, 189, 248, ' + this.opacity + ')';
            ctx.fill();
        }}
    }}

    for (let i = 0; i < PARTICLE_COUNT; i++) particles.push(new Particle());

    function connectParticles() {{
        for (let i = 0; i < particles.length; i++) {{
            for (let j = i + 1; j < particles.length; j++) {{
                const dx = particles[i].x - particles[j].x;
                const dy = particles[i].y - particles[j].y;
                const dist = Math.sqrt(dx * dx + dy * dy);
                if (dist < 150) {{
                    ctx.beginPath();
                    ctx.moveTo(particles[i].x, particles[i].y);
                    ctx.lineTo(particles[j].x, particles[j].y);
                    ctx.strokeStyle = 'rgba(56, 189, 248, ' + (0.06 * (1 - dist / 150)) + ')';
                    ctx.lineWidth = 0.5;
                    ctx.stroke();
                }}
            }}
        }}
    }}

    function animate() {{
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        particles.forEach(p => {{ p.update(); p.draw(); }});
        connectParticles();
        requestAnimationFrame(animate);
    }}
    animate();
}})();

// === Number animation ===
document.querySelectorAll('.stat-value[data-target]').forEach(el => {{
    const target = parseInt(el.dataset.target);
    const duration = 1200;
    const start = performance.now();
    function tick(now) {{
        const elapsed = now - start;
        const progress = Math.min(elapsed / duration, 1);
        const eased = 1 - Math.pow(1 - progress, 3);
        el.textContent = Math.round(target * eased);
        if (progress < 1) requestAnimationFrame(tick);
    }}
    requestAnimationFrame(tick);
}});

// === Chart.js global config ===
Chart.defaults.color = 'rgba(240, 240, 245, 0.5)';
Chart.defaults.borderColor = 'rgba(56, 189, 248, 0.08)';

const chartOptions = (yLabel, suggestedMin, suggestedMax) => ({{
    responsive: true,
    maintainAspectRatio: false,
    animation: {{ duration: 1500, easing: 'easeOutQuart' }},
    plugins: {{
        legend: {{
            display: true,
            position: 'top',
            labels: {{
                font: {{ size: 11, family: "'Rajdhani', sans-serif" }},
                boxWidth: 12,
                boxHeight: 2,
                padding: 16,
                color: 'rgba(240, 240, 245, 0.6)'
            }}
        }},
        tooltip: {{
            backgroundColor: 'rgba(17, 24, 39, 0.95)',
            borderColor: 'rgba(56, 189, 248, 0.2)',
            borderWidth: 1,
            titleFont: {{ family: "'Rajdhani', sans-serif" }},
            bodyFont: {{ family: "'Rajdhani', sans-serif" }},
            padding: 10,
            cornerRadius: 8,
        }}
    }},
    scales: {{
        y: {{
            title: {{ display: true, text: yLabel, font: {{ size: 11 }}, color: 'rgba(240,240,245,0.4)' }},
            suggestedMin, suggestedMax,
            grid: {{ color: 'rgba(56, 189, 248, 0.05)' }},
            ticks: {{ font: {{ size: 10 }}, color: 'rgba(240,240,245,0.4)' }}
        }},
        x: {{
            grid: {{ display: false }},
            ticks: {{ font: {{ size: 10 }}, color: 'rgba(240,240,245,0.3)', maxRotation: 45 }}
        }}
    }},
    elements: {{
        point: {{ radius: 3, hoverRadius: 6, borderWidth: 0, backgroundColor: 'rgba(56, 189, 248, 0.8)' }},
        line: {{ tension: 0.4, borderWidth: 2 }}
    }},
    interaction: {{ intersect: false, mode: 'index' }}
}});

// BP chart with gradient fill
const bpCtx = document.getElementById('bpChart').getContext('2d');
const sysGradient = bpCtx.createLinearGradient(0, 0, 0, 220);
sysGradient.addColorStop(0, 'rgba(255, 71, 87, 0.2)');
sysGradient.addColorStop(1, 'rgba(255, 71, 87, 0.0)');
const diaGradient = bpCtx.createLinearGradient(0, 0, 0, 220);
diaGradient.addColorStop(0, 'rgba(56, 189, 248, 0.2)');
diaGradient.addColorStop(1, 'rgba(56, 189, 248, 0.0)');

new Chart(bpCtx, {{
    type: 'line',
    data: {{
        labels: {bp_dates},
        datasets: [
            {{ label: '收缩压 SYS', data: {bp_sys}, borderColor: '#ff4757', backgroundColor: sysGradient, fill: true, pointBackgroundColor: '#ff4757' }},
            {{ label: '舒张压 DIA', data: {bp_dia}, borderColor: '#38bdf8', backgroundColor: diaGradient, fill: true, pointBackgroundColor: '#38bdf8' }}
        ]
    }},
    options: chartOptions('mmHg', 60, 160)
}});

// HR chart
const hrCtx = document.getElementById('hrChart').getContext('2d');
const hrGradient = hrCtx.createLinearGradient(0, 0, 0, 220);
hrGradient.addColorStop(0, 'rgba(46, 213, 115, 0.25)');
hrGradient.addColorStop(1, 'rgba(46, 213, 115, 0.0)');

new Chart(hrCtx, {{
    type: 'line',
    data: {{
        labels: {hr_dates},
        datasets: [{{ label: '心率 BPM', data: {hr_vals}, borderColor: '#2ed573', backgroundColor: hrGradient, fill: true, pointBackgroundColor: '#2ed573' }}]
    }},
    options: chartOptions('bpm', 50, 110)
}});

// Glucose chart
const gluCtx = document.getElementById('gluChart').getContext('2d');
const gluGradient = gluCtx.createLinearGradient(0, 0, 0, 220);
gluGradient.addColorStop(0, 'rgba(255, 165, 2, 0.25)');
gluGradient.addColorStop(1, 'rgba(255, 165, 2, 0.0)');

new Chart(gluCtx, {{
    type: 'line',
    data: {{
        labels: {glu_dates},
        datasets: [{{ label: '空腹血糖', data: {glu_vals}, borderColor: '#ffa502', backgroundColor: gluGradient, fill: true, pointBackgroundColor: '#ffa502' }}]
    }},
    options: chartOptions('mmol/L', 4.0, 7.0)
}});
</script>
</body>
</html>'''


if __name__ == '__main__':
    import sys
    db_path = sys.argv[1] if len(sys.argv) > 1 else 'health_log.db'
    output = sys.argv[2] if len(sys.argv) > 2 else 'dashboard.html'

    print("正在生成健康仪表盘...")
    data = get_dashboard_data(db_path)
    html = generate_html(data)

    with open(output, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"仪表盘已生成: {output}")
    print(f"  - 指标记录: {data['stats']['total_metrics']}天")
    print(f"  - 活跃药品: {data['stats']['active_meds']}种")
    print(f"  - 预警数: {len(data['alerts']['overdue']) + len(data['alerts']['low_stock']) + len(data['alerts']['expired'])}")
    print(f"  - 待办数: {data['stats']['pending_followups']}项")
