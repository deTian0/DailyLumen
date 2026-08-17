-- 每日复盘数据库 schema
-- 单一数据源：所有每日复盘的结构化字段都落在这张表
-- 约束说明：CHECK 用于拦截脏数据，四维 1-10、质量 0-100、布尔 0/1、数值非负

CREATE TABLE IF NOT EXISTS daily_reviews (
    -- 主键：日期 (YYYY-MM-DD)，每天唯一一条
    date            TEXT PRIMARY KEY,          -- 2026-08-05
    weekday         TEXT,                       -- 周二
    iso_week        INTEGER,                    -- ISO 周号 (周一起)
    month           INTEGER,                    -- 月份索引 202608 (便于跨月查询)
    training_day    INTEGER
        CHECK (training_day IN (0, 1)),        -- 1=训练日 0=否

    -- 健康子指标
    sleep_h         REAL
        CHECK (sleep_h IS NULL OR sleep_h >= 0),
    sleep_quality   INTEGER
        CHECK (sleep_quality IS NULL OR (sleep_quality BETWEEN 0 AND 100)),
    bedtime         INTEGER,                    -- 入睡时间: 距 00:00 的分钟数 (00:39 -> 39)
    supps_done      INTEGER
        CHECK (supps_done IN (0, 1)),          -- 1=补剂全完成 0=否
    exercise_min    INTEGER
        CHECK (exercise_min IS NULL OR exercise_min >= 0),
    commute_done    INTEGER
        CHECK (commute_done IN (0, 1)),        -- 1=通勤完成 0=否
    diet_kcal       INTEGER
        CHECK (diet_kcal IS NULL OR diet_kcal >= 0),
    meals_count     INTEGER
        CHECK (meals_count IS NULL OR (meals_count BETWEEN 0 AND 6)),
    breakfast_on_time INTEGER
        CHECK (breakfast_on_time IN (0, 1)),   -- 1=早餐按时 0=否
    phone_h         REAL
        CHECK (phone_h IS NULL OR phone_h >= 0),

    -- 工作 / 学习 / 生活
    deepwork_h      REAL
        CHECK (deepwork_h IS NULL OR deepwork_h >= 0),
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

-- 索引: 按 ISO 周快速聚合
CREATE INDEX IF NOT EXISTS idx_iso_week ON daily_reviews(iso_week);
CREATE INDEX IF NOT EXISTS idx_month ON daily_reviews(month);
