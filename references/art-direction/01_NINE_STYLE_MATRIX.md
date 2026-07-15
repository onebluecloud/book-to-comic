# 九大风格矩阵与自动选择

## 1. 定位矩阵

| style_id | 正式定位 | 最适合 | 主要风险 |
|---|---|---|---|
| `manga` | Manga Cinematic B&W | 强情绪、人物冲突、心理机制拟人化、动作与反应 | 角色变成通用动漫脸、无墨线的灰色插画、连续多格同一机位 |
| `webtoon-manhwa` | Polished Vertical Webtoon | 手机竖滑、人物关系、都市故事、情绪递进 | 把普通横页直接裁成长图、小屏无法辨认动作、全员同脸 |
| `manhua` | Modern Chinese Full-Color Manhua | 中文社媒、都市与历史、中国文化内容、现实题材 | 现代书被强制古风、所有人物同一网红脸、服装与年代错位 |
| `franco-belgian-bd` | Ligne Claire European Album | 社科和历史、观点解释、旅行与冒险、复杂场景 | 把 BD 固定成幼儿圆头、背景模糊或随意、厚涂油画感 |
| `editorial` | Adult Symbolic Editorial Cartoon | 认知和哲学、社会科学、商业观点、成人幽默 | 堆砌多个隐喻、变成儿童插画、变成扁平企业图库 |
| `comic-strip` | Newspaper Gag Strip | 轻知识、日常解释、角色反差、反转 | 火柴人、四格重复同姿势、笑点只能靠大段旁白解释 |
| `doodle` | Controlled Hand-Drawn Doodle | 生活方式、心理与自我成长、读书笔记、亲切解释 | 火柴人、杂乱不可读、像低清草稿 |
| `retro-halftone` | American Retro Print Comic | 封面、强钩子、观点对抗、戏剧冲突 | 只加网点滤镜、所有脸被点阵破坏、色彩超过控制范围 |
| `ink-sketch` | Literary Pen-and-Ink | 文学、哲学、历史、严肃社科 | 像未完成速写、排线噪声覆盖脸、材质无法区分 |

## 2. 自动选择算法

用户只输入书名时，不询问风格。系统根据 Art Brief 形成十个 0–5 分轴：

```text
emotion, plot, abstract_ideas, humor, mobile,
historical_world, text_density, premium_editorial, action, warmth
```

推荐分数：

```text
style_score =
  0.18 * narrative_fit
+ 0.16 * emotional_fit
+ 0.14 * platform_fit
+ 0.12 * visualizability
+ 0.10 * world_fit
+ 0.10 * audience_fit
+ 0.08 * text_fit
+ 0.07 * production_stability
+ 0.05 * differentiation
```

初筛后执行硬规则：

- 需要纯黑白、高情绪、动作和心理冲突：优先 `manga`。
- 需要手机竖滑、人物关系和全彩：优先 `webtoon-manhwa`。
- 需要中文文化、历史或现实环境准确：优先 `manhua`。
- 需要复杂环境和观点清晰度：优先 `franco-belgian-bd`。
- 需要一图一喻、哲学和社会观察：优先 `editorial`。
- 需要短幽默和反转：优先 `comic-strip`。
- 需要亲切、手账和生活方式：优先 `doodle`。
- 需要冲击力、封面和对抗：优先 `retro-halftone`。
- 需要文学、历史和严肃氛围：优先 `ink-sketch`。

## 2.1 细分风格二级选择

顶层 `style_id` 只解决大方向；`variant_id` 必须从该风格的 `selection.variants` 里选，并且必须等于 `substyles[].id`。子风格不是额外菜单项，而是同一大风格内部的生产语法锁。

| style_id | 优先考虑的子风格 |
|---|---|
| `manga` | `gekiga-cinematic`, `shonen-kinetic`, `shojo-romance`, `josei-everyday`, `classic-screentone`, `yonkoma-gag`, `chibi-sd-comic` |
| `webtoon-manhwa` | `romance-polished`, `romance-fantasy`, `urban-drama`, `action-cinematic`, `thriller-horror-scroll`, `slice-of-life-soft-color`, `campus-office-drama` |
| `manhua` | `modern-urban`, `historical-elegant`, `wuxia-action`, `xianxia-fantasy`, `ink-accented`, `lianhuanhua-retro`, `social-realism` |
| `franco-belgian-bd` | `brussels-clear-line`, `marcinelle-comic-dynamic`, `atom-style-retro-modern`, `realistic-adventure`, `semi-realistic-travel`, `big-nose-humor`, `watercolor-album` |
| `editorial` | `political-satire`, `symbolic-minimal`, `dry-gag`, `conceptual-texture`, `literary-graphic-essay`, `infographic-explainer`, `surreal-metaphor` |
| `comic-strip` | `gag-a-day`, `daily-bw`, `sunday-color`, `continuity-story`, `warm-color-slice-of-life`, `satirical-strip`, `single-panel-gag` |
| `doodle` | `sketchnote-visual-notes`, `notebook-warm`, `marker-color`, `annotated-knowledge`, `diary-comic`, `whiteboard-explainer`, `zine-diy` |
| `retro-halftone` | `benday-pop-print`, `american-golden-pulp`, `retro-romance-horror`, `pop-poster`, `noir-pulp-cover`, `war-propaganda-print`, `cmyk-misregister` |
| `ink-sketch` | `crosshatch-noir`, `literary-pen`, `fine-line-portrait`, `travel-journal`, `stipple-texture`, `woodcut-expression`, `ink-wash-muted` |

选择时按书的题材、平台、情绪强度、动作强度、时代地域和用户显式偏好排序。若两个子风格接近，先做内部 style proof；不要把两个视觉语法互相抵触的子风格混在同一话里。

## 2.2 市场偏好加权

自动选择默认优先当前市场更容易被用户接受的子风格，但前提是内容信号匹配。配置来源是 `presets/market_style_preferences.json`，不是写死在 prompt 里的口号。

优先加权的主流方向：

- Romance / romantasy：`webtoon-manhwa / romance-polished`, `webtoon-manhwa / romance-fantasy`
- Action / fantasy：`webtoon-manhwa / action-cinematic`, `manga / shonen-kinetic`
- 中文武侠/仙侠：`manhua / wuxia-action`, `manhua / xianxia-fantasy`
- 移动端都市剧情：`webtoon-manhwa / urban-drama`
- 读书号和知识漫画：`doodle / sketchnote-visual-notes`, `editorial / infographic-explainer`, `editorial / symbolic-minimal`

硬规则：热门风格只能“加权”，不能替代内容适配。哲学、社科、商业和政治类书，不应因为 romance/action 热门就强行改成恋爱韩漫或战斗漫画；中国古代武侠/仙侠内容，也不应只因目标平台是 mobile 就被抢成通用韩漫动作。

## 3. 内部 Style Proof

当第一名与第二名差距小于阈值时，系统可自动生成内部测试板，不让用户参与：

1. 同一主角半身；
2. 同一室内建立镜头；
3. 同一关键道具特写；
4. 同一高情绪反应。

只比较风格签名、角色重复性、场景可读性和叙事适配度；不要比较完全不同的内容。Style Proof 是内部 QA 资产，不进入最终漫画。

## 4. 评分数据

具体轴分值见 `presets/style_selection_matrix.json`。这些值是启发式初始值，应通过实际生成结果和用户反馈迭代，而不是当成不可改变的事实。
