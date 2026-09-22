"""测试用的样例复盘文本与期望行。"""

# 标准 DailyLumen 格式：末尾 ```data 代码块 + 带时段的打卡小节
SAMPLE_MD = """# 每日复盘 · 2026-08-05（二）

## 一、日常打卡

**晨间（起床后）**

- [x] 补剂：CoQ10 ×1 ＋ Exia 早3
- [ ] 早餐 08:00–09:00
- [x] 护肤

## 附录 · 系统数据

```data
日期: 2026-08-05
星期: 二
训练日: yes
睡眠时长_h: 6.42
睡眠质量: 84
入睡时间: 00:39
运动时长_min: 0
饮食热量_kcal: 1199
碳水_g: 150
脂肪_g: 40
蛋白质_g: 55
三餐情况: 早✓午✓晚✗
早餐按时: yes
手机屏幕_h: 10.9
深度工作_h: 0
学习投入_h: 1.5
生活投入_h: 2.0
健康分: 4
工作分: 6
学习分: 6
生活分: 5
一句话总结: 测试样例
```
"""

# 旧写法打卡：无时段小节标题 + 多项合并 + 名称变体
LEGACY_TRACKS_MD = """# 每日复盘 · 2026-08-06（三）

## 一、日常打卡

- [x] 补剂：复合维生素B族 ×1 ＋ MoveFree 红色 ×1
- [ ] 补剂：Exia晚3
- [x] 早餐

## 附录 · 系统数据

```data
日期: 2026-08-06
星期: 三
训练日: no
```
"""

# 无数据块、纯 key:value 散落的文本（兼容用户直接发）
PROSE_MD = """date: 2026-08-10
星期: 日
训练日: no
睡眠时长_h: 7.5
睡眠质量: 90
入睡时间: 23:10
"""

# 期望 parse_text(SAMPLE_MD) 解析出的关键字段
EXPECTED_SAMPLE = {
    "date": "2026-08-05",
    "sleep_h": 6.42,
    "sleep_quality": 84,
    "bedtime": 39,          # 00:39
    "meals_count": 2,       # 早✓午✓晚✗
    "carbs_g": 150,         # 碳水 (g)
    "fat_g": 40,            # 脂肪 (g)
    "protein_g": 55,        # 蛋白质 (g)
    # 打卡归一化：一条「补剂：A ＋ B」裂成两个规范项；护肤命中规范项
    # 早餐是通用项（有独立字段），不进 personal_tracks
    "_personal_tracks": [
        ("服药", "coq10@morning", "coq10", "CoQ10 ×1", 1),
        ("服药", "exia_am@morning", "exia_am", "Exia 早3", 1),
        ("护肤", "skincare", "skincare", "护肤", 1),
    ],
    "phone_h": 10.9,
    "deepwork_h": 0,
    "learn_h": 1.5,
    "life_h": 2.0,
    "health_score": 4,
    "work_score": 6,
    "learn_score": 6,
    "life_score": 5,
    "system_score": 5.25,   # (4+6+6+5)/4
}
