"""
HealthGuardian - 记忆管理模块
实现三层记忆架构：语义记忆、情景记忆、工作记忆
借鉴 self-improving-agent 的多记忆设计
"""

import json
import os
from datetime import datetime
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict


@dataclass
class SemanticPattern:
    """语义记忆 - 健康规律与模式"""
    id: str                         # 模式 ID (pat-YYYY-MM-DD-NNN)
    name: str                       # 模式名称
    category: str                   # 类别
    pattern: str                    # 模式描述
    problem: str                    # 解决什么问题
    solution: str                   # 解决方案
    confidence: float = 0.5         # 置信度 0-1
    applications: int = 0           # 被应用次数
    created: str = ''               # 创建日期
    source: str = ''                # 来源


@dataclass
class EpisodicMemory:
    """情景记忆 - 具体健康事件"""
    id: str                         # 记忆 ID (ep-YYYY-MM-DD-NNN)
    timestamp: str                  # 事件时间
    event_type: str                 # 事件类型（指标异常/就诊/用药变化/症状发作）
    situation: str                  # 发生了什么
    outcome: str                    # 结果
    lesson: str                     # 经验教训
    related_pattern: Optional[str] = None  # 关联的模式 ID
    confidence: float = 0.8


class MemoryManager:
    """HealthGuardian 记忆管理器"""

    def __init__(self, memory_dir: str = None):
        """
        初始化记忆管理器

        Args:
            memory_dir: 记忆目录路径（默认为 Skill 目录下的 memory/）
        """
        if memory_dir is None:
            memory_dir = os.path.join(os.path.dirname(__file__), 'memory')
        self.memory_dir = memory_dir
        self.semantic_path = os.path.join(memory_dir, 'health-patterns.json')
        self.episodic_dir = os.path.join(memory_dir, 'episodic')
        os.makedirs(self.episodic_dir, exist_ok=True)

    # ========== 语义记忆操作 ==========

    def load_semantic_patterns(self) -> Dict:
        """加载语义记忆（健康规律库）"""
        if not os.path.exists(self.semantic_path):
            return {'patterns': {}, 'health_rules': {}}
        with open(self.semantic_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def save_semantic_patterns(self, data: Dict) -> None:
        """保存语义记忆"""
        data['version'] = data.get('version', '1.0')
        data['description'] = 'HealthGuardian 语义记忆 - 健康规律与模式库'
        with open(self.semantic_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def add_pattern(self, pattern: SemanticPattern) -> str:
        """
        新增健康规律模式

        Returns:
            模式 ID
        """
        if not pattern.id:
            date_str = datetime.now().strftime('%Y-%m-%d')
            pattern.id = f"pat-{date_str}-001"
            pattern.created = date_str

        data = self.load_semantic_patterns()
        if 'patterns' not in data:
            data['patterns'] = {}

        data['patterns'][pattern.id] = {
            'id': pattern.id,
            'name': pattern.name,
            'source': pattern.source,
            'confidence': pattern.confidence,
            'applications': pattern.applications,
            'created': pattern.created,
            'last_validated': datetime.now().strftime('%Y-%m-%d'),
            'category': pattern.category,
            'pattern': pattern.pattern,
            'problem': pattern.problem,
            'solution': pattern.solution,
            'target_metrics': [],
            'target_skills': ['HealthGuardian'],
        }
        self.save_semantic_patterns(data)
        return pattern.id

    def get_patterns(self, category: Optional[str] = None) -> List[Dict]:
        """获取健康规律模式"""
        data = self.load_semantic_patterns()
        patterns = list(data.get('patterns', {}).values())
        if category:
            patterns = [p for p in patterns if p.get('category') == category]
        return sorted(patterns, key=lambda x: x.get('confidence', 0), reverse=True)

    def get_health_rules(self) -> Dict:
        """获取健康规则"""
        data = self.load_semantic_patterns()
        return data.get('health_rules', {})

    def apply_pattern(self, pattern_id: str) -> bool:
        """标记模式被应用（增加应用次数）"""
        data = self.load_semantic_patterns()
        if pattern_id in data.get('patterns', {}):
            data['patterns'][pattern_id]['applications'] = \
                data['patterns'][pattern_id].get('applications', 0) + 1
            self.save_semantic_patterns(data)
            return True
        return False

    # ========== 情景记忆操作 ==========

    def add_episodic_memory(self, memory: EpisodicMemory) -> str:
        """
        新增情景记忆（具体健康事件）

        Args:
            memory: 情景记忆数据

        Returns:
            记忆 ID
        """
        if not memory.id:
            date_str = datetime.now().strftime('%Y-%m-%d')
            memory.id = f"ep-{date_str}-001"
            memory.timestamp = datetime.now().isoformat()

        year = memory.timestamp[:4]
        year_dir = os.path.join(self.episodic_dir, year)
        os.makedirs(year_dir, exist_ok=True)

        filename = f"{memory.id}.json"
        filepath = os.path.join(year_dir, filename)

        data = {
            'id': memory.id,
            'timestamp': memory.timestamp,
            'event_type': memory.event_type,
            'situation': memory.situation,
            'outcome': memory.outcome,
            'lesson': memory.lesson,
            'related_pattern': memory.related_pattern,
            'confidence': memory.confidence,
        }
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return memory.id

    def get_episodic_memories(self, year: Optional[str] = None,
                               event_type: Optional[str] = None,
                               limit: int = 20) -> List[Dict]:
        """
        查询情景记忆

        Args:
            year: 按年份筛选
            event_type: 按事件类型筛选
            limit: 最大返回数
        """
        memories = []
        target_dir = os.path.join(self.episodic_dir, year) if year else self.episodic_dir

        if not os.path.exists(target_dir):
            return memories

        if year:
            # 读取指定年份目录
            for fname in os.listdir(target_dir):
                if fname.endswith('.json'):
                    with open(os.path.join(target_dir, fname), 'r', encoding='utf-8') as f:
                        mem = json.load(f)
                        if event_type and mem.get('event_type') != event_type:
                            continue
                        memories.append(mem)
        else:
            # 递归读取所有年份
            for yr in sorted(os.listdir(self.episodic_dir)):
                yr_path = os.path.join(self.episodic_dir, yr)
                if os.path.isdir(yr_path):
                    for fname in os.listdir(yr_path):
                        if fname.endswith('.json'):
                            with open(os.path.join(yr_path, fname), 'r', encoding='utf-8') as f:
                                mem = json.load(f)
                                if event_type and mem.get('event_type') != event_type:
                                    continue
                                memories.append(mem)

        memories.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        return memories[:limit]

    # ========== 经验提取（进化闭环核心） ==========

    def extract_and_learn(self, event_type: str, situation: str,
                          outcome: str, lesson: str,
                          db_manager=None) -> Dict:
        """
        从一次健康事件中提取经验并学习

        1. 记录情景记忆
        2. 尝试抽象为模式（如果类似事件 >= 2次）
        3. 如果生成了新模式，返回模式信息

        Args:
            event_type: 事件类型
            situation: 发生了什么
            outcome: 结果
            lesson: 经验教训
            db_manager: 数据库管理器（可选，用于跨表分析）

        Returns:
            {"episodic_id": "...", "pattern_created": bool, "pattern_id": "..."}
        """
        # 1. 记录情景记忆
        ep_memory = EpisodicMemory(
            id='', timestamp='', event_type=event_type,
            situation=situation, outcome=outcome, lesson=lesson,
        )
        ep_id = self.add_episodic_memory(ep_memory)

        # 2. 检查是否有类似的已有情景记忆
        similar = self.get_episodic_memories(event_type=event_type, limit=10)
        similar_count = len([s for s in similar
                            if s['id'] != ep_id and lesson.lower() in s.get('lesson', '').lower()])

        pattern_created = False
        pattern_id = None

        # 3. 如果类似经验 >= 5次，抽象为模式（避免数据量少时产生伪模式）
        if similar_count >= 5:
            pattern = SemanticPattern(
                id='', name=lesson[:50],
                category=f'learned_{event_type}',
                pattern=lesson,
                problem=situation[:100],
                solution=outcome[:100],
                confidence=0.7 + similar_count * 0.1,
                source=f'episodic_learning_{event_type}',
            )
            pattern_id = self.add_pattern(pattern)
            pattern_created = True

        return {
            'episodic_id': ep_id,
            'pattern_created': pattern_created,
            'pattern_id': pattern_id,
        }

    # ========== 记忆摘要 ==========

    def get_memory_summary(self) -> Dict:
        """获取记忆库摘要"""
        patterns = self.get_patterns()
        memories = self.get_episodic_memories(limit=100)
        rules = self.get_health_rules()

        return {
            'total_patterns': len(patterns),
            'total_episodic': len(memories),
            'rule_categories': list(rules.keys()),
            'recent_patterns': patterns[:3],
            'recent_memories': memories[:3],
        }
