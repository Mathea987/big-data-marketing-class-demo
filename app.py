"""
开学第一课互动演示：大数据猜猜我是谁
功能：学生填表（星座/爱好/旅游偏好/消费习惯） -> 后台自动画像 -> 推荐可能喜欢的东西
用途：让市场营销大专生直观理解"数据采集 -> 标签 -> 推荐"的大数据营销闭环
"""

from flask import Flask, request, redirect, url_for, render_template, jsonify, session
from datetime import datetime
import os
import json
import threading

app = Flask(__name__)
app.secret_key = "bigdata_demo_secret_key"

# 数据存储：内存列表 + JSON 文件持久化（兼容不支持文件型 SQLite 的环境）
DATA_FILE = os.path.join(os.path.dirname(__file__), "students.json")
_lock = threading.Lock()
_store = {"next_id": 1, "students": []}


def _load():
    """从 JSON 文件加载数据到内存"""
    global _store
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                _store = json.load(f)
        except (json.JSONDecodeError, IOError):
            _store = {"next_id": 1, "students": []}


def _save():
    """将内存数据持久化到 JSON 文件"""
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(_store, f, ensure_ascii=False, indent=2)


def init_db():
    """初始化/加载已有数据（幂等）"""
    _load()


@app.before_request
def ensure_db():
    """确保每个请求前已加载数据"""
    if not _store["students"] and _store["next_id"] == 1:
        _load()


# ============ 推荐引擎（规则匹配，模拟用户画像）============

# 画像标签权重规则：根据字段命中情况累加分数，最终取最高分标签
# 这是简化的"用户画像 + 匹配规则"，对应 Excel 里的规则表

ZODIAC_GROUP = {
    "探险派": ["白羊座", "狮子座", "射手座"],
    "务实派": ["金牛座", "处女座", "摩羯座"],
    "社交派": ["双子座", "天秤座", "水瓶座"],
    "文艺派": ["巨蟹座", "天蝎座", "双鱼座"],
}

# 每个画像标签对应的推荐内容（海南场景）
RECOMMENDATIONS = {
    "海岛探险家": {
        "tags": ["户外", "运动", "探险"],
        "desc": "🏄 推荐：万宁冲浪 + 五指山徒步 + 露营装备租赁",
        "reason": "你热爱户外与运动，海南的阳光海岸就是你的游乐场",
    },
    "精明旅行者": {
        "tags": ["省钱", "性价比"],
        "desc": "💰 推荐：三亚经济型酒店 + 免税店折扣清单 + 本地小吃地图",
        "reason": "你注重性价比，用最少的钱玩出最地道的海南",
    },
    "颜值打卡党": {
        "tags": ["拍照", "网红", "颜值"],
        "desc": "📸 推荐：蜈支洲岛 + 亚龙湾热带天堂 + 天涯海角日落路线",
        "reason": "你爱记录美好，海南的每一处风景都是朋友圈大片",
    },
    "社交达人": {
        "tags": ["社交", "交友", "热闹"],
        "desc": "🎉 推荐：三亚酒吧街 + 海岛音乐节 + 青年旅舍拼房",
        "reason": "你喜欢热闹与结识新朋友，海南的夜生活等你来嗨",
    },
    "慢生活爱好者": {
        "tags": ["安静", "文艺", "放松"],
        "desc": "📚 推荐：骑楼老街 + 文昌铜鼓岭 + 精品民宿手冲咖啡",
        "reason": "你追求宁静与文艺，慢下来才能读懂海南的韵味",
    },
    "美食探险家": {
        "tags": ["美食"],
        "desc": "🥥 推荐：椰子鸡 + 清补凉 + 海鲜夜市 + 文昌鸡老店",
        "reason": "你是地道吃货，海南的味道会让你念念不忘",
    },
    "购物狂欢族": {
        "tags": ["购物"],
        "desc": "🛍️ 推荐：三亚国际免税城 + 海口万象城 + 伴手礼清单",
        "reason": "你热衷剁手，海南离岛免税是你的天堂",
    },
}


def build_profile(student):
    """根据学生数据生成用户画像标签"""
    zodiac = student.get("zodiac", "")
    hobbies = [h.strip() for h in student.get("hobbies", "").split(",") if h.strip()]
    travel = student.get("travel", "")
    shopping = student.get("shopping", "")

    # 1. 星座分组贡献一个基础标签
    zodiac_tag = None
    for group, signs in ZODIAC_GROUP.items():
        if zodiac in signs:
            zodiac_tag = group
            break

    # 2. 统计兴趣关键词命中
    all_text = " ".join(hobbies + [travel, shopping])

    # 3. 计算每个推荐标签的得分
    scores = {}
    for label, info in RECOMMENDATIONS.items():
        score = 0
        for tag in info["tags"]:
            if tag in all_text:
                score += 1
        # 星座分组匹配额外加分
        if zodiac_tag and zodiac_tag in label:
            score += 0.5
        # 消费倾向加分
        if label == "精明旅行者" and shopping == "价格":
            score += 1
        if label == "颜值打卡党" and shopping == "颜值":
            score += 1
        if label == "购物狂欢族" and shopping == "品牌":
            score += 1
        if label == "慢生活爱好者" and travel == "放松":
            score += 1
        scores[label] = score

    # 4. 取最高分标签；若全为0，返回默认"待探索旅行者"
    best = max(scores, key=scores.get)
    if scores[best] <= 0:
        return {
            "label": "随性探索者",
            "desc": "🌴 推荐：三亚湾椰梦长廊 + 一场说走就走的自驾环岛",
            "reason": "你的喜好很随性，海南处处都有惊喜等你发现",
        }
    return {"label": best, **RECOMMENDATIONS[best]}


# ============ 路由 ============

@app.route("/")
def index():
    """学生填表页"""
    return render_template("index.html")


@app.route("/submit", methods=["POST"])
def submit():
    """接收学生提交，生成画像并展示结果"""
    data = request.form
    nickname = data.get("nickname", "").strip() or "匿名同学"
    zodiac = data.get("zodiac", "")
    hobbies_list = data.getlist("hobbies")  # 多选
    travel = data.get("travel", "")
    shopping = data.get("shopping", "")

    hobbies_str = ",".join(hobbies_list)

    # 存入内存 + 持久化到 JSON 文件
    with _lock:
        sid = _store["next_id"]
        _store["next_id"] += 1
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _store["students"].append({
            "id": sid,
            "nickname": nickname,
            "zodiac": zodiac,
            "hobbies": hobbies_str,
            "travel": travel,
            "shopping": shopping,
            "created_at": now,
        })
        _save()

    # 生成画像
    profile = build_profile({
        "zodiac": zodiac,
        "hobbies": hobbies_str,
        "travel": travel,
        "shopping": shopping,
    })

    return render_template("result.html",
                           nickname=nickname,
                           zodiac=zodiac,
                           hobbies=hobbies_list,
                           travel=travel,
                           shopping=shopping,
                           profile=profile,
                           student_id=sid)


@app.route("/dashboard")
def dashboard():
    """教师后台：实时数据大屏 + 全部学生画像"""
    with _lock:
        rows = list(reversed(_store["students"]))  # 最新的在前

    students = []
    label_counts = {}
    for r in rows:
        prof = build_profile(dict(r))
        students.append({
            "id": r["id"],
            "nickname": r["nickname"],
            "zodiac": r["zodiac"],
            "hobbies": r["hobbies"].split(",") if r["hobbies"] else [],
            "travel": r["travel"],
            "shopping": r["shopping"],
            "label": prof["label"],
            "desc": prof["desc"],
            "created_at": r["created_at"],
        })
        label_counts[prof["label"]] = label_counts.get(prof["label"], 0) + 1

    # 准备图表数据（标签分布）
    chart_labels = list(label_counts.keys())
    chart_data = list(label_counts.values())

    return render_template("dashboard.html",
                           students=students,
                           total=len(students),
                           chart_labels=chart_labels,
                           chart_data=chart_data)


@app.route("/api/stats")
def api_stats():
    """供大屏轮询的 JSON 接口（实时更新）"""
    with _lock:
        rows = list(_store["students"])
    label_counts = {}
    for r in rows:
        prof = build_profile(dict(r))
        label_counts[prof["label"]] = label_counts.get(prof["label"], 0) + 1
    return jsonify({
        "total": len(rows),
        "labels": list(label_counts.keys()),
        "counts": list(label_counts.values()),
    })


@app.route("/reset", methods=["POST"])
def reset():
    """教师一键清空数据（开学第一课可反复演练）"""
    with _lock:
        _store["next_id"] = 1
        _store["students"] = []
        _save()
    return redirect(url_for("dashboard"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
