-- 每日复盘数据库 schema
-- 单一数据源：所有每日复盘的「通用」结构化字段都落在这张表
-- 约束说明：CHECK 用于拦截脏数据，四维 1-10、质量 0-100、布尔 0/1、数值非负

CREATE TABLE IF NOT EXISTS daily_reviews (
    -- 主键：日期 (YYYY-MM-DD)，每天唯一一条
    date            TEXT PRIMARY KEY,          -- 2026-08-05
    weekday         TEXT,                       -- 周二
    iso_week        INTEGER,                    -- ISO 周号 (周一起)
    month           INTEGER,                    -- 月份索引 202608 (便于跨月查询)
    training_day    INTEGER
        CHECK (training_day IN (0, 1)),        -- 1=训练日 0=否

    -- 健康子指标（通用，人人都有）
    sleep_h         REAL
        CHECK (sleep_h IS NULL OR sleep_h >= 0),
    sleep_quality   INTEGER
        CHECK (sleep_quality IS NULL OR (sleep_quality BETWEEN 0 AND 100)),
    bedtime         INTEGER,                    -- 入睡时间: 距 00:00 的分钟数 (00:39 -> 39)
    exercise_min    INTEGER
        CHECK (exercise_min IS NULL OR exercise_min >= 0),
    exercise_src    TEXT                        -- 运动时长来源: 'record'=字段填报
        CHECK (exercise_src IS NULL OR exercise_src IN ('record', 'derived', 'zero')),
                                                -- 'derived'=由「三件事」描述折算
                                                -- 'zero'=训练日未记录按 0 计（v1.3.2 口径）
                                                -- (NULL=无运动信息)
    commute_done    INTEGER
        CHECK (commute_done IN (0, 1)),        -- 1=通勤完成 0=否
    diet_kcal       INTEGER
        CHECK (diet_kcal IS NULL OR diet_kcal >= 0),
    carbs_g         INTEGER
        CHECK (carbs_g IS NULL OR carbs_g >= 0),      -- 碳水摄入 (g)
    fat_g           INTEGER
        CHECK (fat_g IS NULL OR fat_g >= 0),          -- 脂肪摄入 (g)
    protein_g       INTEGER
        CHECK (protein_g IS NULL OR protein_g >= 0),  -- 蛋白质摄入 (g)
    meals_count     INTEGER
        CHECK (meals_count IS NULL OR (meals_count BETWEEN 0 AND 6)),
    breakfast_on_time INTEGER
        CHECK (breakfast_on_time IN (0, 1)),   -- 1=早餐按时 0=否
    phone_h         REAL
        CHECK (phone_h IS NULL OR phone_h >= 0),

    -- 工作 / 学习 / 生活
    deepwork_h      REAL
        CHECK (deepwork_h IS NULL OR deepwork_h >= 0),
    learn_h         REAL
        CHECK (learn_h IS NULL OR learn_h >= 0),
    life_h          REAL
        CHECK (life_h IS NULL OR life_h >= 0),
    energy          TEXT,                       -- 精力 (可选,文本)
    mood            TEXT,                       -- 心情 (可选,文本)

    -- 四维自评 1-10
    health_score    INTEGER
        CHECK (health_score IS NULL OR (health_score BETWEEN 1 AND 10)),
    work_score      INTEGER
        CHECK (work_score IS NULL OR (work_score BETWEEN 1 AND 10)),
    learn_score     INTEGER
        CHECK (learn_score IS NULL OR (learn_score BETWEEN 1 AND 10)),
    life_score      INTEGER
        CHECK (life_score IS NULL OR (life_score BETWEEN 1 AND 10)),

    -- 派生: 系统分 = 四维均值 (四维度齐全才计算)
    system_score    REAL
        CHECK (system_score IS NULL OR (system_score BETWEEN 1 AND 10)),

    -- 叙事文本 (可选, 存摘要)
    summary         TEXT,

    -- 元数据
    raw_path        TEXT,                       -- 来源 md 文件
    ingested_at     TEXT                        -- 入库时间戳
);

-- 索引由 db.py 在迁移完成后统一创建（见 _create_indexes）：
-- 老库的 personal_tracks 在迁移前没有 item_key 列，索引若写在建表脚本里
-- 会在升级过程中因「引用了尚不存在的列」而报错。

-- 个人定制化打卡（服药 / 护肤 / 自定义）：不计入通用评分，单独统计
-- 与通用表解耦：小伙伴可自定义自己的个人项，无需改表结构
--
-- 【为什么用 track_key 当主键，而不是原始文本 item】
-- 打卡项的手写文本天然不稳定（同一个 CoQ10 可能写成「CoQ10 ×1」
-- 「晨间-CoQ10 ×1 ＋ Exia 早3」等），若直接用文本做键，同一项会裂成
-- 多种形态，依从率无法聚合。因此主键使用 tracks 模块归一化后的规范 ID：
--   item_key  规范项 ID，不含时段（coq10 / exia_am / vitb / movefree / skincare）
--   track_key item_key，时段明确时追加 @<slot>（coq10@morning / movefree@evening）；
--             时段未知则为裸 item_key（movefree）
-- 归一化规则定义在 config.PERSONAL_ITEMS + tracks.py。
CREATE TABLE IF NOT EXISTS personal_tracks (
    date      TEXT NOT NULL,                   -- 关联日期
    track_key TEXT NOT NULL,                   -- 规范 ID（含时段后缀，见上）
    category  TEXT NOT NULL,                   -- 服药 / 护肤 / 自定义类别
    item_key  TEXT NOT NULL,                   -- 规范项 ID（不含时段，用于聚合）
    item      TEXT NOT NULL,                   -- 展示名（如 CoQ10 ×1）
    done      INTEGER
        CHECK (done IS NULL OR done IN (0, 1)),-- 1=完成 0=未完成
    note      TEXT,                            -- 备注
    PRIMARY KEY (date, track_key)
);

-- 体征（体重 / 体脂 / 腰围）：独立指标区，不参与四维评分
-- BMI 不入源、不进库 —— 由 config.PROFILE["height_cm"] + weight_kg 在渲染时算
-- 不设对 daily_reviews 的外键：允许「只称了体重、没写复盘」的日子独立存在
CREATE TABLE IF NOT EXISTS body_metrics (
    date         TEXT PRIMARY KEY,              -- 与 daily_reviews.date 同口径
    weight_kg    REAL
        CHECK (weight_kg IS NULL OR (weight_kg > 0 AND weight_kg < 400)),
    body_fat_pct REAL
        CHECK (body_fat_pct IS NULL OR (body_fat_pct BETWEEN 0 AND 70)),
    waist_cm     REAL
        CHECK (waist_cm IS NULL OR (waist_cm > 0 AND waist_cm < 300)),
    src          TEXT
        CHECK (src IS NULL OR src IN ('scale', 'manual')),  -- 体脂秤截图 / 手填
    note         TEXT
);

-- 训练课（session）+ 动作明细（items）：独立指标区，不直接改四维评分
-- exercise_min 仍是健康分唯一运动输入；明细合计仅在字段为空时派生（R2）
-- 不设对 daily_reviews 的外键：允许「只录了训练、没写复盘」的日子
CREATE TABLE IF NOT EXISTS training_sessions (
    date        TEXT NOT NULL,
    session_key TEXT NOT NULL,        -- 'main' / 'morning' / 'evening'
    plan_name   TEXT,                 -- 课表名（如 'A-胸背'）
    src         TEXT
        CHECK (src IS NULL OR src IN ('lianlian', 'self')),
    total_min   INTEGER
        CHECK (total_min IS NULL OR total_min >= 0),
    note        TEXT,
    PRIMARY KEY (date, session_key)
);

CREATE TABLE IF NOT EXISTS training_items (
    date        TEXT NOT NULL,
    session_key TEXT NOT NULL,
    item_key    TEXT NOT NULL,        -- 归一化动作 key（在 config.TRAINING_MOVES 里）
    item        TEXT NOT NULL,        -- 展示名
    sets        INTEGER,
    reps        INTEGER,
    minutes     REAL,
    load_kg     REAL,
    PRIMARY KEY (date, session_key, item_key)
);

-- 行为习惯（ClickUp「习惯与打卡」快照）：独立指标区，不参与四维评分
-- 与 personal_tracks（补剂/护肤）物理隔离，永不合并（R3）
-- 权威：ClickUp 执行层 → 本表快照（唯一 ClickUp→库写方向）；可从 ClickUp 快照重建
CREATE TABLE IF NOT EXISTS habit_logs (
    date      TEXT NOT NULL,
    habit_key TEXT NOT NULL,        -- 归一化 key（在 config.HABITS 里）
    category  TEXT NOT NULL,        -- 行为习惯（固定值，便于与 personal_tracks 区分）
    item      TEXT NOT NULL,        -- 展示名
    done      INTEGER
        CHECK (done IS NULL OR done IN (0, 1)),
    src       TEXT,                 -- 'clickup'
    note      TEXT,
    PRIMARY KEY (date, habit_key)
);

-- 学习记录（教师角色）：独立指标区，不参与四维评分（G5）
-- 权威：md「附录 · 学习记录」→ ingest；可从 md 100% 重建
CREATE TABLE IF NOT EXISTS learning_logs (
    date      TEXT NOT NULL,
    topic_key TEXT NOT NULL,        -- 归一化主题（config.LEARNING_TOPICS 或 slugify）
    topic     TEXT NOT NULL,        -- 展示名
    minutes   REAL
        CHECK (minutes IS NULL OR minutes >= 0),
    src       TEXT
        CHECK (src IS NULL OR src IN ('clickup', 'self', 'course')),
    artifact  TEXT,                 -- 产出物（笔记 / 代码 / 章节）
    PRIMARY KEY (date, topic_key)
);

-- 复习队列：派生表，必须可从 learning_logs 完全重建（stage 由历史学习次数推算）
-- note 在重建路径上恒为 NULL（不存无法重建的状态）
CREATE TABLE IF NOT EXISTS review_queue (
    topic_key TEXT PRIMARY KEY,
    topic     TEXT NOT NULL,
    stage     INTEGER NOT NULL DEFAULT 0,
    due_date  TEXT NOT NULL,
    last_seen TEXT,
    note      TEXT
);

-- 索引见文件开头说明，由 db.py 统一创建。

-- 食物明细（v9 / M25）：独立指标区，不参与四维评分（G5）
-- 权威：md「附录 · 食物明细」→ ingest；可从 md 100% 重建
-- 无天然主键，seq 是同日表内顺序；kcal 为估算值（不做精确化）
CREATE TABLE IF NOT EXISTS nutrition_items (
    date      TEXT NOT NULL,
    seq       INTEGER NOT NULL
        CHECK (seq >= 0),
    meal      TEXT NOT NULL
        CHECK (meal IN ('breakfast', 'lunch', 'dinner', 'snack', 'other')),
    item      TEXT NOT NULL,
    kcal      REAL
        CHECK (kcal IS NULL OR (kcal >= 0 AND kcal <= 5000)),
    protein_g REAL
        CHECK (protein_g IS NULL OR (protein_g >= 0 AND protein_g <= 500)),
    carb_g    REAL
        CHECK (carb_g IS NULL OR (carb_g >= 0 AND carb_g <= 1000)),
    fat_g     REAL
        CHECK (fat_g IS NULL OR (fat_g >= 0 AND fat_g <= 500)),
    note      TEXT,
    PRIMARY KEY (date, seq)
);

-- 承诺（v10 / M29）：改进点 + 明日 Top 3，独立指标区，不参与四维评分
-- 权威：md「## 三、一个改进点」「## 四、明日 Top 3」→ ingest；可从 md 100% 重建
-- date 记写下承诺那天，对账对象是次日（due 由 date 推导，不落库）
-- bucket 是分类桶（learn / exercise / diet / sleep / phone / work / supplement），
-- 由 core.promises.classify 派生，随「先删后插」同步
CREATE TABLE IF NOT EXISTS promises (
    date   TEXT NOT NULL,
    kind   TEXT NOT NULL
        CHECK (kind IN ('improvement', 'plan')),
    seq    INTEGER NOT NULL
        CHECK (seq >= 0),
    text   TEXT NOT NULL,
    bucket TEXT,
    PRIMARY KEY (date, kind, seq)
);
