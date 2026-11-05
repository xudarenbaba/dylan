"""Closed sets and physiology parameters. Every literal the memory rules use lives here."""

from __future__ import annotations

SCHEMA_VERSION = 2
BRAIN_NAME = "dylan"
PRIVACY_NOTICE = "对话内容和被唤起的记忆会发送给 DeepSeek。"
DEFAULT_MODEL = "deepseek-flash"
DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_TIMEZONE = "Asia/Shanghai"
SECRET_PATTERN = r"sk-[A-Za-z0-9_-]{16,}"
SECRET_MASK = "［密钥已隐去］"

TIMEOUT_SECONDS = 60
BUFFER_TURNS = 12
RECALL_LIMIT = 6
RECALL_CHARS = 1500
AWARENESS_CHARS = 1000

ANCHOR_KIND = "memory"
NODE_KINDS = {
    "person": "人物",
    "animal": "动物",
    "place": "地点",
    "organization": "组织",
    "object": "物品",
    "work": "作品",
    "topic": "话题",
    "time": "时间",
    "emotion": "情绪",
}

MEMORY_TYPES = {
    "innate": "天生",
    "self": "自我认识",
    "event": "事件",
    "session": "相处",
    "period": "时期",
    "fact": "事实",
    "status": "近况",
    "preference": "喜好",
    "habit": "习惯",
    "agreement": "约定",
    "plan": "打算",
    "impression": "印象",
}
SLEEP_ONLY_TYPES = frozenset({"session", "period"})

SOURCES = {
    "innate": "天生",
    "user": "他说的",
    "self": "她自己说的",
    "shared": "一起经历的",
    "inference": "她的推断",
    "reflection": "睡眠时的归纳",
}
RELIABLE_SOURCES = frozenset({"innate", "user", "self", "shared"})
INFERRED_SOURCES = frozenset({"inference", "reflection"})

STATES = {
    "active": "有效",
    "superseded": "过时",
    "done": "已完成",
    "suppressed": "被淡忘",
    "merged": "已合并",
}
RECALLABLE_STATES = frozenset({"active", "superseded", "done"})
CHANGEABLE_STATES = frozenset({"active", "superseded", "done"})

STAGES = {"fresh": "新的", "familiar": "熟悉", "settled": "牢固"}

# name -> (中文, 组, 是否对称)
RELATIONS: dict[str, tuple[str, str, bool]] = {
    "involves": ("涉及", "element", False),
    "happened_on": ("发生在", "element", False),
    "located_at": ("在", "element", False),
    "felt": ("感受到", "element", False),
    "family": ("家人", "social", False),
    "partner": ("恋人", "social", True),
    "friend": ("朋友", "social", True),
    "colleague": ("同事或同学", "social", True),
    "acquainted": ("认识", "social", True),
    "created": ("创造", "social", False),
    "raises": ("养", "possession", False),
    "owns": ("拥有", "possession", False),
    "lives_in": ("住在", "possession", False),
    "works_at": ("在……工作或上学", "possession", False),
    "part_of": ("属于", "possession", False),
    "is_a": ("是一种", "attitude", False),
    "trait": ("特点", "attitude", False),
    "likes": ("喜欢", "attitude", False),
    "dislikes": ("讨厌", "attitude", False),
    "values": ("看重", "attitude", False),
    "good_at": ("擅长", "attitude", False),
    "before": ("之前", "sequence", False),
    "causes": ("导致", "sequence", False),
    "enables": ("促成", "sequence", False),
    "hinders": ("阻碍", "sequence", False),
    "reminds_of": ("让人想起", "sequence", True),
    "supersedes": ("取代", "revision", False),
    "contradicts": ("矛盾", "revision", True),
    "clarifies": ("澄清", "revision", False),
    "adds_to": ("补充", "revision", False),
    "supports": ("支持", "revision", False),
    "opposes": ("反对", "revision", False),
    "derived_from": ("归纳自", "revision", False),
    "completes": ("完成", "revision", False),
    "co_recalled": ("常一起被想起", "grown", True),
}
NODE_RELATIONS = frozenset(
    name for name, (_label, group, _sym) in RELATIONS.items()
    if group in {"social", "possession", "attitude"}
)
MEMORY_LINKS = frozenset(
    {
        "before",
        "causes",
        "enables",
        "hinders",
        "part_of",
        "reminds_of",
        "clarifies",
        "adds_to",
        "supports",
        "opposes",
        "derived_from",
    }
)
# alias -> (canonical, swap ends)
RELATION_ALIASES = {
    "after": ("before", True),
    "because": ("causes", True),
    "caused_by": ("causes", True),
    "leads_to": ("causes", False),
}

PRONOUNS_USER = frozenset({"用户", "对方"})
PRONOUNS_SELF = frozenset({"我", "自己", "助手"})
PRONOUNS_BOTH = frozenset({"我们", "我俩", "我们俩", "咱们", "两人", "我们两个"})
STOP_TERMS = frozenset(
    {
        "我", "你", "他", "她", "它", "我们", "你们", "他们", "她们", "它们", "咱们",
        "自己", "这", "那", "这个", "那个", "什么", "的", "了", "吗", "呢", "啊", "吧",
        "嗯", "哦", "好", "是", "在", "有", "用户", "助手",
    }
)
MAX_TERM_CHARS = 12
MAX_CUES = 8
MAX_ALIASES = 6
MAX_NAME_CHARS = 20
STATEMENT_CHARS = 200
DETAIL_CHARS = 500
GIST_CHARS = 20
EVIDENCE_MIN_CHARS = 2

# 编码强度
BASE_STRENGTH = 0.6
IMPORTANCE_STRENGTH = 0.04
EMOTION_STRENGTH = 0.2
DEFAULT_IMPORTANCE = 5

# 遗忘：每日衰减系数
DECAY_PER_DAY = {
    "innate": 0.0,
    "self": 0.003,
    "event": 0.02,
    "session": 0.02,
    "period": 0.005,
    "fact": 0.01,
    "status": 0.12,
    "preference": 0.01,
    "habit": 0.008,
    "agreement": 0.002,
    "plan": 0.02,
    "impression": 0.01,
}
OVERDUE_PLAN_DECAY = 0.08
OVERDUE_GRACE_DAYS = 3
SUPPRESSED_DECAY = 0.5
EMOTION_STABILITY = 0.5
IMPORTANCE_STABILITY_BASE = 0.6
IMPORTANCE_STABILITY_STEP = 0.08

# 变熟
STAGE_DECAY_SCALE = {"fresh": 1.0, "familiar": 0.6, "settled": 0.25}
STAGE_FLOOR = {"fresh": 0.0, "familiar": 0.3, "settled": 0.6}
FAMILIAR_DAYS = 3
FAMILIAR_COUNT = 3
SETTLED_AGE_DAYS = 7
SETTLED_DAYS = 5
SETTLED_COUNT = 6
SETTLED_STRENGTH = 0.6

# 细节先淡：强度不低于这些值时停在 0、1、2 层，否则第 3 层
LEVEL_THRESHOLDS = (0.6, 0.4, 0.2)

# 记得多清楚
CLEAR_STRENGTH = 0.5
VAGUE_STRENGTH = 0.2
GUESS_CONFIDENCE = 0.5
INFERRED_CONFIDENCE = 0.5
INFERRED_CONFIDENCE_CAP = 0.7
EVIDENCE_FOR_STEP = 0.1
EVIDENCE_AGAINST_SCALE = 0.8

# 想起会加强
SHOWN_BUMP = 0.02
USED_BUMP = 0.08
REINFORCE_BUMP = 0.12
UPDATE_BUMP = 0.05
SPACING_DAYS = 3.0
SPACING_FLOOR = 0.25

# 联想
NODE_WEIGHT = 1.0
CUE_WEIGHT = 0.9
COACTIVATION_MIN = 2
SPREAD_DECAY = 0.2
SPREAD_FLOOR = 0.15
SPREAD_MAX_HOPS = 4
HUB_DEGREE = 8
CONTEXT_WEIGHTS = (1.0, 0.5, 0.3)
CARRY_WEIGHT = 0.4
DATE_WEIGHT = 0.7
RECALL_FLOOR = 0.15
DEFAULT_LINK_WEIGHT = 0.6
GROWN_LINK_WEIGHT = 0.3
HEBBIAN_ETA = 0.05
SUPERSEDED_CONDUCT = 0.5

CLARITY = {
    "clear": "清楚记得",
    "vague": "有点模糊",
    "feeling": "我的感觉",
    "guess": "只是猜测",
    "past": "以前是这样",
    "conflict": "说法有出入",
    "trace": "记得有这回事",
}
WEEKDAYS = ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日")

# 自己长出来的连线随时间变弱
SYNAPSE_HALF_LIFE_HOURS = 1440.0
SYNAPSE_HALF_LIFE_GROWTH = 0.5

# 清理
PRUNE_LINK_WEIGHT = 0.05
PRUNE_LINK_DAYS = 30
FORGET_STRENGTH = 0.1
FORGET_TRACE_DAYS = 180
SUPPRESS_FADE_DAYS = 3
SUPPRESS_DROP_DAYS = 30
MERGED_DROP_DAYS = 30

# 心情
MOOD_HALF_LIFE_HOURS = 6.0
MOOD_FLOOR = 0.15
DEFAULT_BASELINE_MOOD = "开朗"

# 常驻意识
STATUS_AWARE_DAYS = 7
PLAN_AWARE_AHEAD_DAYS = 1
PLAN_AWARE_OVERDUE_DAYS = 3
SELF_AWARE_LIMIT = 3

# 每次写入的上限
MAX_NOTE_OPS = 8
MAX_SLEEP_OPS = 16
MAX_BIRTH_OPS = 40
MAX_SUPPRESS = 5
MAX_NODES = 8
MAX_RELATIONS = 8
MAX_LINKS = 6
MAX_CANDIDATES = 12
MAX_SLEEP_CANDIDATES = 24
SESSION_CANDIDATES = 4
LABEL_CHARS = 10
TRIGGER_CHARS = 60
SUMMARY_CHARS = 300
PENDING_MAX_ATTEMPTS = 3

# 窗口开着时，隔一会儿让她自己决定要不要先说。关着窗口不做这次决定。
HER_TURN = "〔她先说〕"
INITIATIVE_IDLE_MIN_MINUTES = 1
INITIATIVE_IDLE_MAX_MINUTES = 10
INITIATIVE_LINE_CHARS = 120
