# 崩铁 2026 人气票数追踪

实时抓取 [starrailawards.com Vote2026](https://www.starrailawards.com/Vote2026/index.html) 每个角色的票数，写入 SQLite 持久化，并通过本地网页面板查看不同颜色的折线对比图。重启程序后历史数据依然保留。

---

## 给客户用（小白版）

### 第 1 步：安装 Python（只需一次）

下载并安装 **Python 3.11**：
> https://www.python.org/downloads/release/python-3119/

页面下方找到 **Windows installer (64-bit)** 下载安装。

⚠️ **安装时一定要勾选最下面的 `Add python.exe to PATH`！** 否则 bat 会找不到 Python。

如果嫌 3.11 太老也可以装 3.10 / 3.12，都能跑。不要装 3.13（部分库还没适配好）。

### 第 2 步：安装运行需要的库（只需一次）

双击 **`安装依赖.bat`**，等命令窗口出现 `Done!` 即完成，按任意键关闭。

### 第 3 步：日常使用

双击 **`启动.bat`**，4 秒后浏览器会自动弹出面板。
- 想停掉：直接关闭那个黑色命令窗口。
- 数据存在 `votes.db` 里，下次启动还能看到历史曲线。

---

## 文件结构

```
app.py                # Flask 服务 + 后台抓取线程
extract_characters.py # 一次性脚本：从 characterOld.js 生成 characters.json
characters.json       # 角色 id/姓名/性别/图标
templates/index.html  # 面板页面
static/app.js         # 前端逻辑（Chart.js）
static/style.css      # 样式
votes.db              # 自动创建的 SQLite 数据库（.gitignore 内）
requirements.txt
安装依赖.bat           # 客户一键安装
启动.bat               # 客户一键启动
```

## 开发者用法

```powershell
python -m pip install -r requirements.txt
python app.py
# 然后打开 http://127.0.0.1:5000
```

## 阶段日程（来自上游脚本）

| 阶段 | 时间（北京时间）              | 候选人数 |
| ---- | ----------------------------- | -------- |
| 5    | 2026/05/05 12:00 - 05/08 23:59 | 71（女 48 / 男 23）— 第一轮 |
| 6    | 2026/05/09 22:00 - 05/12 23:59 | 40（女 25 / 男 15）— 第二轮（第一轮 TOP 入围） |
| 7    | 2026/05/13 12:00 - 05/15 23:59 | 复活赛 |
| 8    | 2026/05/16 12:00 - 05/19 23:59 | 决赛 |

阶段之间会有"投票未开启"窗口，那时上游 `lstV` 字段为空，所有人显示 0 票，是正常的（程序会提示）。
程序会每小时自动从 `https://static.appoint.icu/Railvote/characterb.js` 拉一次最新候选名单，跨阶段无需重启。

## 数据库结构

```sql
CREATE TABLE votes (
    ts          INTEGER NOT NULL,  -- unix 秒
    vote_id     INTEGER NOT NULL,  -- 对应 characters.json 的 id
    vote_count  INTEGER NOT NULL,
    PRIMARY KEY (vote_id, ts)
);
```

只有当票数发生变化时才会写新行，长期运行也不会爆库。

## 可调参数（在 `app.py` 顶部）

| 常量 | 默认 | 说明 |
| --- | --- | --- |
| `POLL_INTERVAL` | 10 | 抓取间隔（秒） |
| `ROSTER_REFRESH_INTERVAL` | 3600 | 角色名单从上游刷新的间隔（秒） |
| `DB_PATH` | `votes.db` | 数据库文件位置 |

## 角色列表更新

程序运行时每小时自动从 `characterb.js` 拉一次。手动刷新：

```powershell
python extract_characters.py            # 当前阶段（默认，约 40 人）
python extract_characters.py --full     # 全历史角色（71 人，调试用）
```
