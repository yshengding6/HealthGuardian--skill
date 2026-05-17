"""
HealthGuardian v3 - 固定格式健康仪表盘生成器
三区布局：优先区(指标+预警) → 用药区(清单+依从率) → 详情区(图表+日志)
配色、字体、区块顺序固定，不随会话变化
"""

import json
import os
import sys
import sqlite3
from datetime import datetime, timedelta
from html import escape as h


def get_dashboard_data(db_path: str = 'health_log.db') -> dict:
    """从数据库获取仪表盘所需的全部数据"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    _skill_dir = os.path.dirname(os.path.abspath(__file__))
    if _skill_dir not in sys.path:
        sys.path.insert(0, _skill_dir)

    data = {
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'today': datetime.now().strftime('%Y-%m-%d'),
        'metrics': {
            'dates': [],
            'systolic_bp': [],
            'diastolic_bp': [],
            'heart_rate': [],
            'fasting_glucose': [],
            'sleep_hours': [],
            'steps': [],
        },
        'latest_metrics': None,
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
            'critical': [],
            'warning': [],
            'overdue': [],
            'low_stock': [],
            'expired': [],
        },
        'med_checklist': None,
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
        d = row['date'][5:]
        data['metrics']['dates'].append(d)
        data['metrics']['systolic_bp'].append(row['systolic_bp'])
        data['metrics']['diastolic_bp'].append(row['diastolic_bp'])
        data['metrics']['heart_rate'].append(row['heart_rate'])
        data['metrics']['fasting_glucose'].append(row['fasting_glucose'])
        data['metrics']['sleep_hours'].append(row['sleep_hours'])
        data['metrics']['steps'].append(row['steps'])
    data['stats']['total_metrics'] = len(data['metrics']['dates'])

    # 2. 最新一次指标（用于第一区大数字）
    c.execute("""
        SELECT date, systolic_bp, diastolic_bp, heart_rate, fasting_glucose
        FROM daily_metrics
        WHERE systolic_bp IS NOT NULL OR heart_rate IS NOT NULL OR fasting_glucose IS NOT NULL
        ORDER BY date DESC LIMIT 1
    """)
    latest = c.fetchone()
    if latest:
        data['latest_metrics'] = dict(latest)

    # 3. 活跃药品
    c.execute("""
        SELECT id, name, dosage, frequency, remaining_quantity,
               expiry_date, low_stock_threshold, med_type, schedule_time
        FROM medications
        WHERE is_active = 1
        ORDER BY schedule_time ASC, name ASC
    """)
    for row in c.fetchall():
        data['medications'].append(dict(row))
    data['stats']['active_meds'] = len(data['medications'])

    # 4. 就医待办
    c.execute("""
        SELECT * FROM follow_up_actions
        WHERE status != '已完成' AND status != '已取消'
        ORDER BY priority ASC, due_date ASC
    """)
    for row in c.fetchall():
        data['follow_ups'].append(dict(row))
    data['stats']['pending_followups'] = len(data['follow_ups'])

    # 5. 预警分级
    # 关键预警：过期待办
    c.execute("""
        SELECT title, due_date, priority FROM follow_up_actions
        WHERE status NOT IN ('已完成', '已取消')
        AND due_date IS NOT NULL AND due_date < date('now','localtime')
        ORDER BY priority ASC
    """)
    data['alerts']['overdue'] = [dict(r) for r in c.fetchall()]

    # 关键预警：已过期药品
    c.execute("""
        SELECT name, expiry_date, remaining_quantity FROM medications
        WHERE is_active = 1 AND expiry_date < date('now','localtime')
    """)
    data['alerts']['expired'] = [dict(r) for r in c.fetchall()]

    # 关键预警：药品用完
    c.execute("""
        SELECT name, remaining_quantity FROM medications
        WHERE is_active = 1 AND remaining_quantity = 0
    """)
    data['alerts']['critical'] = [dict(r) for r in c.fetchall()]

    # 一般预警：药品余量低
    c.execute("""
        SELECT name, remaining_quantity, low_stock_threshold, frequency
        FROM medications
        WHERE is_active = 1 AND remaining_quantity > 0
        AND remaining_quantity <= low_stock_threshold
    """)
    data['alerts']['low_stock'] = [dict(r) for r in c.fetchall()]

    # 6. 最近健康日志
    c.execute("""
        SELECT date, category, title, severity FROM health_logs
        ORDER BY date DESC, id DESC LIMIT 10
    """)
    for row in c.fetchall():
        data['health_logs'].append(dict(row))
    data['stats']['total_logs'] = len(data['health_logs'])

    # 7. 服药依从性 + 用药清单
    try:
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
        # 获取今日用药清单
        data['med_checklist'] = tmp_db.get_daily_med_checklist()
        tmp_db.close()
    except Exception:
        for med in data['medications']:
            med['adherence'] = 0
            med['days_taken'] = 0

    # 8. 指标预警（用于第一区）
    try:
        if data['latest_metrics']:
            from db_manager import DatabaseManager, DailyMetric
            tmp_db = DatabaseManager(db_path)
            lm = data['latest_metrics']
            metric = DailyMetric(
                id=None, date=lm.get('date', ''),
                systolic_bp=lm.get('systolic_bp'),
                diastolic_bp=lm.get('diastolic_bp'),
                heart_rate=lm.get('heart_rate'),
                fasting_glucose=lm.get('fasting_glucose'),
            )
            metric_alerts = tmp_db.check_alerts(metric)
            data['metric_alerts'] = [{'item': a.item, 'level': a.level, 'message': a.message} for a in metric_alerts]
            tmp_db.close()
        else:
            data['metric_alerts'] = []
    except Exception:
        data['metric_alerts'] = []

    conn.close()
    return data


def generate_html(data: dict) -> str:
    """生成固定三区布局的健康仪表盘"""

    def clean_series(dates, values):
        result_dates, result_values = [], []
        for d, v in zip(dates, values):
            if v is not None:
                result_dates.append(d)
                result_values.append(v)
        return json.dumps(result_dates), json.dumps(result_values)

    # 血压收缩/舒张联合过滤：只保留两者都非 None 的点
    def clean_bp_series(dates, sys_vals, dia_vals):
        result_dates, result_sys, result_dia = [], [], []
        for d, s, di in zip(dates, sys_vals, dia_vals):
            if s is not None and di is not None:
                result_dates.append(d)
                result_sys.append(s)
                result_dia.append(di)
        return json.dumps(result_dates), json.dumps(result_sys), json.dumps(result_dia)

    bp_dates, bp_sys, bp_dia = clean_bp_series(
        data['metrics']['dates'],
        data['metrics']['systolic_bp'],
        data['metrics']['diastolic_bp'])
    hr_dates, hr_vals = clean_series(data['metrics']['dates'], data['metrics']['heart_rate'])
    glu_dates, glu_vals = clean_series(data['metrics']['dates'], data['metrics']['fasting_glucose'])

    # === 第一区：优先区 ===
    # 最新指标大数字
    lm = data.get('latest_metrics') or {}
    bp_display = f"{lm.get('systolic_bp', '--')}/{lm.get('diastolic_bp', '--')}" if lm.get('systolic_bp') else '--/--'
    hr_display = str(lm.get('heart_rate', '--')) if lm.get('heart_rate') else '--'
    glu_display = str(lm.get('fasting_glucose', '--')) if lm.get('fasting_glucose') else '--'

    # 指标状态：基于 metric_alerts 而非硬编码
    def get_metric_alert_for(item_name, metric_alerts):
        for a in metric_alerts:
            if a['item'] == item_name:
                return a
        return None

    metric_alerts = data.get('metric_alerts', [])

    def bp_status(s, d, alerts):
        if s is None: return '#888', '--'
        alert = get_metric_alert_for('血压', alerts)
        if alert:
            color_map = {'严重': '#ff4757', '中度': '#ff4757', '轻微': '#ffa502'}
            label_map = {'严重': '偏高', '中度': '偏高', '轻微': '正常偏高'}
            return color_map.get(alert['level'], '#ffa502'), label_map.get(alert['level'], '偏高')
        return '#2ed573', '正常'

    def hr_status(v, alerts):
        if v is None: return '#888', '--'
        alert = get_metric_alert_for('心率', alerts)
        if alert:
            color_map = {'严重': '#ff4757', '中度': '#ff4757', '轻微': '#ffa502'}
            label_map = {'严重': '异常', '中度': '异常', '轻微': '偏高'}
            return color_map.get(alert['level'], '#ffa502'), label_map.get(alert['level'], '异常')
        return '#2ed573', '正常'

    def glu_status(v, alerts):
        if v is None: return '#888', '--'
        alert = get_metric_alert_for('空腹血糖', alerts)
        if alert:
            color_map = {'严重': '#ff4757', '中度': '#ff4757', '轻微': '#ffa502'}
            label_map = {'严重': '偏高', '中度': '偏高', '轻微': '注意'}
            return color_map.get(alert['level'], '#ffa502'), label_map.get(alert['level'], '偏高')
        return '#2ed573', '正常'

    bp_color, bp_label = bp_status(lm.get('systolic_bp'), lm.get('diastolic_bp'), metric_alerts)
    hr_color, hr_label = hr_status(lm.get('heart_rate'), metric_alerts)
    glu_color, glu_label = glu_status(lm.get('fasting_glucose'), metric_alerts)

    # 药物完成率
    mc = data.get('med_checklist') or {}
    med_total = mc.get('total', 0)
    med_completed = mc.get('completed', 0)
    med_rate = mc.get('completion_rate', 0)
    med_rate_color = '#2ed573' if med_rate >= 80 else ('#ffa502' if med_rate >= 50 else '#ff4757')

    # 预警横幅
    critical_alerts = []
    for a in data['alerts']['overdue']:
        critical_alerts.append(f'[过期待办] {h(a["title"])} (截止: {a["due_date"]})')
    for a in data['alerts']['expired']:
        critical_alerts.append(f'[药品过期] {h(a["name"])} ({a["expiry_date"]})')
    for a in data['alerts']['critical']:
        critical_alerts.append(f'[药品用完] {h(a["name"])}')

    warning_alerts = []
    for a in data['alerts']['low_stock']:
        warning_alerts.append(f'[余量低] {h(a["name"])} 剩余{a["remaining_quantity"]}片')
    for a in data.get('metric_alerts', []):
        warning_alerts.append(f'[{a["item"]}] {a["message"]}')

    # === 第二区：用药区 ===
    # 用药清单按时段分组
    SCHEDULE_LABELS = {'早': '早晨', '中': '中午', '晚': '晚间', '睡前': '睡前'}
    checklist_by_time = {}
    for item in (mc.get('checklist') or []):
        slot = item.get('schedule_slot', '早')
        if slot not in checklist_by_time:
            checklist_by_time[slot] = []
        checklist_by_time[slot].append(item)

    checklist_html = ''
    for schedule in ['早', '中', '晚', '睡前']:
        items = checklist_by_time.get(schedule, [])
        if not items:
            continue
        checklist_html += f'<div style="margin-bottom:12px;">'
        checklist_html += f'<div style="font-size:11px;color:rgba(56,189,248,0.7);margin-bottom:6px;letter-spacing:1px;">{SCHEDULE_LABELS.get(schedule, schedule)}</div>'
        for item in items:
            if item['status'] == '已服':
                icon = '<span style="color:#2ed573;">&#10003;</span>'
                detail = f'<span style="color:rgba(255,255,255,0.4);font-size:11px;">{item.get("log_time","")}</span>'
            elif item['status'] == '部分':
                icon = '<span style="color:#ffa502;">&#9672;</span>'
                detail = f'<span style="color:rgba(255,165,2,0.6);font-size:11px;">部分服用</span>'
            else:
                icon = '<span style="color:#ff4757;">&#9675;</span>'
                detail = f'<span style="color:rgba(255,71,87,0.6);font-size:11px;">未记录</span>'
            med_type_tag = ''
            if item.get('med_type') and item['med_type'] != '长期':
                med_type_tag = f'<span style="font-size:10px;color:rgba(255,165,2,0.6);margin-left:4px;">[{item["med_type"]}]</span>'
            checklist_html += f'''
            <div style="display:flex;align-items:center;gap:8px;padding:6px 10px;margin-bottom:4px;border-radius:6px;background:rgba(255,255,255,0.02);">
                <span style="font-size:14px;">{icon}</span>
                <span style="flex:1;font-size:13px;color:#e8e8e8;">{h(item["name"])}</span>
                {med_type_tag}
                <span style="font-size:11px;color:rgba(255,255,255,0.35);">{item["dosage"]}</span>
                {detail}
            </div>'''
        checklist_html += '</div>'

    if not checklist_html:
        checklist_html = '<div style="padding:16px;text-align:center;font-size:13px;color:var(--text-dim);">暂无活跃药品</div>'

    # 依从率进度条
    adherence_html = ''
    for m in data['medications']:
        adh = m.get('adherence', 0)
        if adh >= 80:
            bar_color = '#2ed573'
            bar_bg = 'linear-gradient(90deg, #2ed573, #7bed9f)'
        elif adh >= 50:
            bar_color = '#ffa502'
            bar_bg = 'linear-gradient(90deg, #ffa502, #ffc048)'
        else:
            bar_color = '#ff4757'
            bar_bg = 'linear-gradient(90deg, #ff4757, #ff6b7a)'
        adherence_html += f'''
        <div style="display:flex;align-items:center;gap:10px;padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.04);">
            <span style="width:120px;font-size:12px;color:#e8e8e8;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{h(m["name"])}</span>
            <div style="flex:1;height:6px;background:rgba(255,255,255,0.06);border-radius:3px;overflow:hidden;">
                <div style="height:6px;background:{bar_bg};border-radius:3px;width:{min(adh,100)}%;transition:width 1.5s cubic-bezier(0.4,0,0.2,1);"></div>
            </div>
            <span style="width:42px;text-align:right;font-size:13px;font-weight:600;color:{bar_color};">{adh}%</span>
        </div>'''

    # === 第三区：详情区 ===
    # 就医待办
    followups_html = ''
    for f in data['follow_ups'][:8]:
        priority_color = {'高': '#ff4757', '中': '#ffa502', '低': '#2ed573'}
        color = priority_color.get(f['priority'], '#888')
        due = f.get('due_date', '') or '无截止日期'
        followups_html += f'''
        <div style="display:flex;align-items:center;gap:10px;padding:8px 12px;margin-bottom:6px;border-radius:8px;background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.06);">
            <span style="width:8px;height:8px;border-radius:50%;background:{color};flex-shrink:0;box-shadow:0 0 8px {color}40;"></span>
            <span style="flex:1;font-size:13px;color:#e8e8e8;">{h(f['title'])}</span>
            <span style="font-size:11px;color:rgba(255,255,255,0.4);">{due}</span>
        </div>'''

    # 健康日志
    logs_html = ''
    for l in data['health_logs'][:5]:
        severity_color = {'轻': '#2ed573', '中': '#ffa502', '重': '#ff4757'}
        scolor = severity_color.get(l.get('severity', ''), '#888')
        logs_html += f'''
        <div style="padding:6px 0;font-size:12px;color:rgba(255,255,255,0.7);border-bottom:1px solid rgba(255,255,255,0.04);">
            <span style="color:rgba(255,255,255,0.3);margin-right:8px;">{l["date"]}</span>
            <span style="color:{scolor};margin-right:4px;">&#9679;</span>
            <span style="color:rgba(255,255,255,0.4);margin-right:4px;">[{h(l["category"])}]</span>
            {h(l["title"])}
        </div>'''
    if not logs_html:
        logs_html = '<div style="padding:12px;text-align:center;font-size:12px;color:rgba(255,255,255,0.3);">暂无健康日志</div>'

    # 统计总数
    total_critical = len(critical_alerts)
    total_warning = len(warning_alerts)

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
    }}

    /* Zone labels */
    .zone-label {{
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 14px;
        padding: 0 4px;
    }}

    .zone-label .zone-icon {{
        width: 20px; height: 20px;
        border-radius: 4px;
        display: flex; align-items: center; justify-content: center;
        font-size: 11px;
        font-weight: 700;
    }}

    .zone-label .zone-text {{
        font-size: 13px;
        font-weight: 500;
        letter-spacing: 2px;
        text-transform: uppercase;
    }}

    .zone-priority .zone-icon {{ background: rgba(255,71,87,0.2); color: #ff4757; }}
    .zone-priority .zone-text {{ color: #ff6b7a; }}

    .zone-medication .zone-icon {{ background: rgba(56,189,248,0.2); color: #38bdf8; }}
    .zone-medication .zone-text {{ color: #38bdf8; }}

    .zone-detail .zone-icon {{ background: rgba(46,213,115,0.2); color: #2ed573; }}
    .zone-detail .zone-text {{ color: #2ed573; }}

    .zone-divider {{
        height: 1px;
        background: linear-gradient(90deg, transparent, rgba(56,189,248,0.15), transparent);
        margin: 24px 0;
    }}

    /* Stat cards */
    .stats-row {{
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 12px;
        margin-bottom: 16px;
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
        font-size: 26px;
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

    .stat-sub {{
        font-size: 11px;
        margin-top: 4px;
        font-weight: 500;
    }}

    /* Completion bar in stat card */
    .completion-bar-bg {{
        height: 4px;
        background: rgba(255,255,255,0.06);
        border-radius: 2px;
        margin-top: 8px;
        overflow: hidden;
    }}

    .completion-bar-fill {{
        height: 4px;
        border-radius: 2px;
        transition: width 1.5s cubic-bezier(0.4,0,0.2,1);
    }}

    /* Alert banner */
    .alert-banner {{
        border-radius: 10px;
        padding: 12px 16px;
        margin-bottom: 8px;
        font-size: 12px;
    }}

    .alert-critical {{
        background: rgba(255,71,87,0.08);
        border: 1px solid rgba(255,71,87,0.2);
        color: #ff6b7a;
    }}

    .alert-warning {{
        background: rgba(255,165,2,0.08);
        border: 1px solid rgba(255,165,2,0.2);
        color: #ffc048;
    }}

    .alert-ok {{
        background: rgba(46,213,115,0.06);
        border: 1px dashed rgba(46,213,115,0.2);
        color: rgba(46,213,115,0.7);
    }}

    /* Card */
    .card {{
        background: var(--bg-card);
        backdrop-filter: blur(10px);
        border-radius: 14px;
        padding: 18px;
        margin-bottom: 16px;
        border: 1px solid var(--border-glow);
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
    <!-- Header -->
    <div class="header">
        <div class="logo">
            <div class="logo-icon">&#9829;</div>
            <h1>HealthGuardian</h1>
        </div>
        <div class="meta">{data['generated_at']} &middot; {data['today']}</div>
    </div>

    <!-- ===== 第一区：优先区 ===== -->
    <div class="zone-label zone-priority">
        <div class="zone-icon">!</div>
        <span class="zone-text">优先区 Priority</span>
    </div>

    <div class="stats-row">
        <div class="stat-card">
            <div class="stat-value" style="color:{bp_color};">{bp_display}</div>
            <div class="stat-label">最新血压 mmHg</div>
            <div class="stat-sub" style="color:{bp_color};">{bp_label}</div>
        </div>
        <div class="stat-card">
            <div class="stat-value" style="color:{hr_color};">{hr_display}</div>
            <div class="stat-label">最新心率 bpm</div>
            <div class="stat-sub" style="color:{hr_color};">{hr_label}</div>
        </div>
        <div class="stat-card">
            <div class="stat-value" style="color:{glu_color};">{glu_display}</div>
            <div class="stat-label">最新血糖 mmol/L</div>
            <div class="stat-sub" style="color:{glu_color};">{glu_label}</div>
        </div>
        <div class="stat-card">
            <div class="stat-value" style="color:{med_rate_color};">{med_completed}/{med_total}</div>
            <div class="stat-label">今日用药完成</div>
            <div class="completion-bar-bg">
                <div class="completion-bar-fill" style="width:{min(med_rate, 100)}%;min-width:{'2px' if med_rate > 0 else '0'};background:linear-gradient(90deg,{med_rate_color},{med_rate_color}aa);"></div>
            </div>
            <div class="stat-sub" style="color:{med_rate_color};">{med_rate}%</div>
        </div>
    </div>

    <!-- 预警横幅 -->
    {''.join(f'<div class="alert-banner alert-critical"><span style="opacity:0.7;margin-right:6px;">&#9632;</span>{a}</div>' for a in critical_alerts)}
    {''.join(f'<div class="alert-banner alert-warning"><span style="opacity:0.7;margin-right:6px;">&#9650;</span>{a}</div>' for a in warning_alerts)}
    {f'<div class="alert-banner alert-ok">&#10003; 系统运行正常，暂无预警</div>' if not critical_alerts and not warning_alerts else ''}

    <div class="zone-divider"></div>

    <!-- ===== 第二区：用药区 ===== -->
    <div class="zone-label zone-medication">
        <div class="zone-icon">R</div>
        <span class="zone-text">用药区 Medication</span>
    </div>

    <div class="grid-2">
        <div class="card">
            <div class="card-title">今日用药清单 Checklist</div>
            {checklist_html}
        </div>
        <div class="card">
            <div class="card-title">依从率 Adherence (30天)</div>
            {adherence_html if adherence_html else '<div style="font-size:13px;color:var(--text-dim);text-align:center;padding:20px;">暂无数据</div>'}
        </div>
    </div>

    <div class="zone-divider"></div>

    <!-- ===== 第三区：详情区 ===== -->
    <div class="zone-label zone-detail">
        <div class="zone-icon">D</div>
        <span class="zone-text">详情区 Details</span>
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
        HealthGuardian v3.0 &middot; Powered by WorkBuddy
    </div>
</div>

<script>
// Particle background
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

// Chart.js global config
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

// BP chart
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
    mc = data.get('med_checklist') or {}
    if mc:
        print(f"  - 今日用药: {mc.get('completed', 0)}/{mc.get('total', 0)} ({mc.get('completion_rate', 0)}%)")
    else:
        print(f"  - 今日用药: 加载失败")
    print(f"  - 预警数: {len(data['alerts']['critical']) + len(data['alerts']['low_stock']) + len(data['alerts']['expired'])}")
    print(f"  - 待办数: {data['stats']['pending_followups']}项")
