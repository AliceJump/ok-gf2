# Terminology Glossary (Chinese -> Global / Steam English)

This project began in Chinese, and its CN task set still is. This file maps each Chinese game term to
the exact wording the **Global / Steam** client of Girls' Frontline 2: Exilium shows on screen. The
Global task set under `src/global/` matches that English wording directly, so this table is also the
reference for what those tasks look for.

The authority is the Global client itself, not a dictionary. Several terms are deliberately *not*
literal translations, because the literal form does not exist in the English client. For example
`尘烟前线` is **Gunsmoke Frontline**, not "Dust Front", and `活动层` is simply the **Crew Deck**.

Use this file whenever you translate anything in this repository so that the README, the guides in
`docs/en/`, and any future UI work all agree.

## Status legend

| Status | Meaning |
|---|---|
| confirmed | Read directly off the Global client UI. |
| unstable | Renamed by the game every event, so no fixed English name exists. Describe it by function instead. |
| n/a | No in-game equivalent. This is a name the bot invented for one of its own options. |

## Main screen

| Chinese | Global term | Status |
|---|---|---|
| 战役推进 | Campaign | confirmed |
| 活动 | Event / Time-Limited Events | confirmed |
| 要务 | Commissions | confirmed |
| 公共区 | Crew Deck | confirmed |
| 班组 | Platoon | confirmed |
| 编队 | Formation | confirmed |
| 商店 / 商城 | Shop | confirmed |
| 招募 | Recruitment | confirmed |
| 改造室 | Refitting Room | confirmed |
| 巡录 / 大月卡 | Voyage | confirmed |

## Campaign -> Supply Missions

Where materials are farmed. These consume Intelligence Puzzle.

| Chinese | Global term | Status |
|---|---|---|
| 体力本 (as a category) | Supply Missions | confirmed |
| 深度搜索 | In-Depth Search | confirmed |
| 军备解析 | Equipment Analysis | confirmed |
| 决策构象 | Cognitive Configuration | confirmed |
| 定向 | Targeted Study | confirmed |
| 标准化同步 | Standardizing Sync | confirmed |

## Campaign -> Combat Simulations

| Chinese | Global term | Status |
|---|---|---|
| 模拟作战 | Combat Simulations | confirmed |
| 神经调查 | Neural Survey | confirmed |
| 首领挑战 | Boss Fight | confirmed |
| 竞技场 | Combat Exercises | confirmed |
| 峰值推定 | Peak Value Assessment | confirmed |
| 扩编实练 | Expansion Drills | confirmed |
| - | Target Practice | confirmed |

Note that **Boss Fight** is singular in the Global client. Do not write "Boss Fights".

## Commissions

| Chinese | Global term | Status |
|---|---|---|
| 常规要务 | Regular Commissions | confirmed |
| 边界推进 | Boundary Push | confirmed |
| 边界推进 sub-modes | Breakthrough, Phase Clash | confirmed |

Regular Commissions is a hub that links out to Expansion Drills, Boss Fight, Peak Value Assessment,
and Boundary Push. Those modes also live under Campaign, so the same stage is reachable two ways.

## Platoon

| Chinese | Global term | Status |
|---|---|---|
| 尘烟前线 / 尘烟 | Gunsmoke Frontline | confirmed |
| 补给 | Resupply | confirmed |
| - | Essential Tasks | confirmed |

Platoon's **Essential Tasks** is a Platoon-only list. It is a different thing from `要务`
(Commissions) on the main screen, even though both translate loosely as "duties".

## Crew Deck (the Elmo)

| Chinese | Global term | Status |
|---|---|---|
| 公共区 | Crew Deck | confirmed |
| 活动层 | Crew Deck | confirmed |
| 喝水 | Tea Time (at the coffee machine) | confirmed |
| 吃饭 | Delicious Cuisine (at the kitchen) | confirmed |
| 浇花 | Manage Flower (by Helena) | confirmed |
| 调度室 | Dispatch Room | confirmed |
| 自主循环 | started with the Start Loop button | confirmed |
| - | Lounge | confirmed |

`公共区` and `活动层` both become **Crew Deck**. Chinese separates the menu entry from the walkable
level, English does not, so let context carry the difference.

The Crew Deck is a walkable 3D area. That is why the Tea Time and Delicious Cuisine options are
key-hold durations: the bot is walking your character to the coffee machine and to the kitchen, so
the timings depend on where your character happens to be standing.

## Event

Every Event has a different title, but the internal structure is always the same.

| Chinese | Global term | Status |
|---|---|---|
| 剧情 | Story | confirmed |
| 物资关卡 / 物资模式 | Supply | confirmed |
| 挑战 | Challenge | confirmed |
| - | the event Shop | confirmed |
| 情报补给 | a reward track advanced by running Supply Missions | unstable |
| 闪耀星愿 | the title of one past limited-time event | unstable |
| 铸碑者的黎明 | an example event title used in the README | unstable |

The event Shop and the reward track are renamed to fit each event's theme, so never hard-code an
English name for them. Describe what they do instead.

## Shop -> Wishlist

| Chinese | Global term | Status |
|---|---|---|
| 心愿单 | Wishlist | confirmed |
| 家具 | Furniture Shop | confirmed |
| 班组 | Platoon Shop | confirmed |
| 调度 | Dispatch Shop | confirmed |
| 讯段 | Battlelog Trading | confirmed |
| 心智 | Neural Integration | confirmed |
| 人形堆栈 | Growth Stack | confirmed |

## Resources

| Chinese | Global term | Status |
|---|---|---|
| 体力 / 理智 | Intelligence Puzzle | confirmed |
| 体力恢复道具 | Access Key | confirmed |

Intelligence Puzzle is the stamina system. It regenerates over time, and one Access Key restores 60.

## Bot option names

These are this program's own labels, not game strings. They get plain descriptive English.

| Chinese | English | Status |
|---|---|---|
| 一键日常 | One-Click Dailies | n/a |
| 周常 | Weekly | n/a |
| 推图 / 清图 | Auto-Clear Campaign Stages | n/a |
| 活动自律 | Auto-Run Event Supply | n/a |
| 自动刷体力 | Auto-Farm Intelligence Puzzle | n/a |
| 领任务 | Claim Commission Rewards | n/a |
| 探索领取 | Claim Boundary Push Rewards | n/a |
| 收菜 | Collect Idle Rewards | n/a |
| 社区每日 | Community Daily Check-In | n/a |
| 购买免费礼包 | Claim Free Packs | n/a |
| 邮件 | Mail | n/a |

### Global task set

These have no Chinese counterpart. They are the labels used by the tasks under `src/global/`, which
only ever run against the English client.

| Label | Where it appears |
|---|---|
| Game Client | The `Region` setting, choosing `Global` or `CN` |
| Global Daily | Task name |
| Global Weekly | Task name |
| Start Loop | Global Daily setting |
| Claim Free Packs | Global Daily setting, same label as the CN one above |
| Run Event Supply | Global Daily setting |
| Event Banner Slots | Which home screen banners to open, nested under `Run Event Supply` |
| Claim Boundary Push Rewards | Global Daily setting, same label as the CN one above |
| Crew Deck | Global Daily setting, off by default |
| Tea Time Walk | Walk timing, nested under `Crew Deck` |
| Delicious Cuisine Walk | Walk timing, nested under `Crew Deck` |
| Claim Peak Value Rewards | Global Weekly setting |
| Run: Go Home, Run: Start Loop, Run: Claim Free Packs, Run: Event Supply, Run: Claim Boundary Push, Run: Claim Peak Value, Run: Crew Deck | One task each, running a single flow |

## Do not translate

- `老王同学OK` is the QQ group join answer. It is a literal password and must stay exactly as-is.
- `docs/dev/i18n_OCR配置流程.md` and `docs/dev/键盘操作体系.md` are real filenames on disk. Link to
  them by their actual Chinese names until those files are themselves renamed.

## Known-bad translations to watch for

The older machine-generated English in `i18n/en_US/LC_MESSAGES/ok.po` and in earlier versions of
the README used literal renderings that do not appear anywhere in the Global client. If you see
any of these, replace them.

| Wrong | Correct |
|---|---|
| War Chess Simulation | (feature is not implemented, see below) |
| Dust Smoke / Dust Front | Gunsmoke Frontline |
| Clear Map Task | Auto-Clear Campaign Stages |
| Arena | Combat Exercises |
| Deep Search | In-Depth Search |
| Armament Analysis | Equipment Analysis |
| Decision Configuration | Cognitive Configuration |
| Stamina Stage | Supply Missions |
| Public Area | Crew Deck |
| Pioneers Task | (feature is not implemented, see below) |

## 兵棋推演 / 开拓之王

Intentionally absent from the tables above. `src/tasks/PioneersTask.py` is an unfinished skeleton and
is not registered in `onetime_tasks` in `src/config.py`, so it never appears in the UI. There is no
working feature to name, and the mode could not be found documented on any English or Chinese site.
Give it a Global name only once the feature actually works.
