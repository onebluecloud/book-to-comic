# 色彩脚本、灯光、镜头与字艺

## 1. Color Script

整话不能只有一个固定滤镜。至少为以下剧情阶段定义色彩：

```text
normal
inciting_event
rising_conflict
turning_point
climax
aftermath
```

每阶段记录：

- 色温；
- 饱和度；
- 明度范围；
- 阴影色；
- 强调色；
- 颜色的叙事作用；
- 禁止颜色。

全彩风格也必须先通过黑白缩略图；颜色不能修复失败的明度结构。

## 2. Motivated Lighting

每格回答：

- 主光从哪里来；
- 环境光是什么颜色；
- 光线为何存在；
- 是否延续上一格；
- 阴影形状是否服从物体；
- 是否为了“电影感”无理由增加轮廓光。

### Material Logic

每个重复角色、场景和关键道具记录 2-3 个材质词：

```text
skin: warm, soft, low-shine
hair: grouped, dark, selective highlight
cloth: matte, heavy, worn
paper: thin, creased, warm-white
wood: dull, scratched, brown
metal: hard-edge, small highlight, cool reflection
```

材质词必须影响 prompt 和 QA：不同材质的高光面积、边缘硬度、纹理密度和受光颜色应不同。若皮肤、头发、布料、金属、木头、纸张看起来像同一种滤镜，视为发布级精修失败。

## 3. Shot Plan

一话 8 格的建议基础节奏：

1. 建立镜头：地点、时代、人物状态；
2. 中景：目标或日常；
3. 道具特写或触发事件；
4. 反应近景；
5. 双人或关系镜头；
6. 力量变化或动作；
7. 极近特写或决定；
8. 结果、余韵或钩子。

这不是固定模板。Skill 应检测连续镜头是否重复，并要求至少覆盖 4 种景别。

### 每格字段

```text
shot_size
camera_angle
lens_feel
focal_point
foreground
midground
background
character_blocking
eyeline
action_vector
negative_space
transition_from
transition_to
lettering_safe_zone
```

## 4. Panel Rhythm

页面构图和分镜实体密度是风格视觉语言的一部分。[S03][S24]

- 高信息建立格后应给低信息反应格；
- 动作格和反应格不能合并成一张海报；
- 连续三格同一景别、同一机位和同一人物大小视为节奏失败；
- Webtoon 的纵向空间可表达距离、时间、情绪和揭示，不只是把横页堆成长条。[S12]
- 每话至少有一个 emotion anchor shot：可记住的具体动作、身体反应、关键道具或环境细节，而不是单纯漂亮近景。
- opening、turning point、final hook 是高风险格；正式 prompt 前先选择焦点和构图目的，必要时做 6-12 个缩略构图方向。

## 5. Lettering Bible

图片模型默认不生成可读文字；最终文字由后期层完成。

### 气泡与旁白

- 标准对话：圆或椭圆气泡；
- 低语：虚线、低对比或更小文字；
- 喊叫：爆发轮廓或加粗；
- 内心：旁白框或明确的思想气泡体系；
- 画外音：带引号的 spoken caption；
- 地点时间：独立 caption；
- 编辑说明：独立 editorial caption。

气泡尾巴应指向说话者嘴部方向，而不是随意指向身体。[S22]

### 中文字艺

- 处理中文标点禁则；
- 控制每行字数和气泡内行数；
- 重要词可通过字重、字号或颜色强调；
- 字体要匹配风格而不是统一使用同一无衬线；
- 不让文字覆盖脸、手、关键道具和动作路径；
- 对白顺序按阅读方向自然串联。
- 每句叠字先判定文案任务：钩子、语境、翻译、情绪、记忆句或行动引导。
- 语气先于润色：严肃/经典作品用克制、具体、可复述的句子，不用震惊体、廉价口水话或鸡汤句。
- 每话保留一条 memory sentence：准确贴书、短、能复述，并且贴着当前画面动作。

### 拟声词

Manga 的拟声词可进入空间深度和动作轨迹，但仍应由后期生成，不由图片模型写伪字。[S25]
