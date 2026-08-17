-- 每日复盘数据库 schema
-- 单一数据源：所有每日复盘的结构化字段都落在这张表

CREATE TABLE IF NOT EXISTS daily_reviews (
    -- 主键：日期 (YYYY-MM-DD)，每天唯一一条
    date            TEXT PRIMARY KEY,          -- 2026-08-05
    weekday         TEXT,                       -- 周二
    iso_week        INTEGER,                    -- ISO 周号 (周一起)
    month           INTEGER,                    -- 月份索引 202608 (便于跨月查询)
    training_day    INTEGER,                    -- 1=训练日 0=否

    -- 健康子指标
    sleep_h         REAL,                       -- 睡眠时长(小时)
    sleep_quality   INTEGER,                    -- 睡眠质量 0-100
    supps_done      INTEGER,                    -- 1=补剂全完成 0=否
    exercise_min    INTEGER,                    -- 正式运动时长(分钟)
    commute_done    INTEGER,                    -- 1=通勤完成 0=否
    diet_kcal       INTEGER,                    -- 饮食热量(kcal)
    meals_count     INTEGER,                    -- 三餐次数
    breakfast_on_time INTEGER,                  -- 1=早餐按时 0=否
    phone_h         REAL,                       -- 手机屏幕(小时)

    -- 工作 / 学习 / 生活
    deepwork_h      REAL,                       -- 深度工作(小时)
    energy          TEXT,                       -- 精力 (可选,文本)
    mood            TEXT,                       -- 心情 (可选,文本)

    -- 四维自评 1-10
    health_score    INTEGER,
    work_score      INTEGER,
    learn_score     INTEGER,
    life_score      INTEGER,

    -- 派生: 系统分 = 四维均值 (四维度齐全才计算)
    system_score    REAL,

    -- 叙事文本 (可选, 存摘要)
    summary         TEXT,

    -- 元数据
    raw_path        TEXT,                       -- 来源 md 文件
    ingested_at     TEXT                        -- 入库时间戳
);

-- 索引: 按 ISO 周快速聚合
CREATE INDEX IF NOT EXISTS idx_iso_week ON daily_reviews(iso_week);
CREATE INDEX IF NOT EXISTS idx_month ON daily_reviews(month);
