# 报纸连环漫画 / Comic Strip — 短节奏幽默

## 1. 风格定义

- **稳定 ID**：`comic-strip`
- **生产名称**：Newspaper Gag Strip
- **传统**：newspaper comic strip
- **格式**：3–6 beat horizontal or card sequence
- **媒介**：clean outline + limited color or B&W
- **边界说明**：重点是节奏与角色关系，不是单纯简笔画。

## 2. 适用范围

**最适合**：轻知识；日常解释；角色反差；反转；短幽默；固定场景对话。

**不优先**：宏大世界观、强写实战争、依赖复杂材质和氛围的内容。

**内置子风格**：`gag-a-day`, `daily-bw`, `sunday-color`, `continuity-story`, `warm-color-slice-of-life`, `satirical-strip`, `single-panel-gag`。

完整适用/排除规则见 `../02_SUBSTYLE_CATALOG.md`。

**交付平台**：`strip`, `card`, `social`, `article`。

## 3. 人物设计

- **真实度**：0.35
- **人体**：简化但不是火柴人；手脚、姿态和动作必须明确。
- **面部**：少量稳定特征和大幅可读表情；角色之间通过头型、鼻型、发型和体块区分。
- **形状与轮廓**：图形清楚、重复性高；角色和道具能在小尺寸快速识别。
- **角色生产规则**：固定角色组合和关系是核心；表演在小格中一眼可读。

人物参考板必须包含：正面、3/4、侧面、背面、全身比例、三种核心表情、两种常用手势、标志道具和不可变化项。

## 4. 线条、黑白与色彩

- **线条**：清洁黑色轮廓，粗细适中；内部细节少；必要时用局部抖动增加手工感。
- **黑白/明度**：大面积白底或浅色；黑块只用于头发、服装或节奏强调。
- **颜色**：轻量平涂，角色色固定；背景色简洁。
- **光线**：通常简化；只保留帮助时间、天气或情绪的信息。
- **纹理**：极少；不能用纹理掩盖表演。

## 5. 场景与物件

- **场景**：固定场景保持机位和道具位置，便于读者迅速进入情境。
- **道具**：少而准；反复出现的道具承担笑点、习惯和身份。

反复地点必须建立平面关系和视觉锚点；关键道具必须记录尺寸、轮廓、材料、所有者、使用方式和剧情状态。

## 6. 镜头、分格与字艺

- **镜头**：以中景和双人镜头为主，关键反应给近景；最后一格可用反应镜头收束。
- **分格**：setup → development → turn → reaction；每格变化明确，不能四格都只是站着说话。
- **字艺**：气泡短，阅读顺序绝对清楚；最后一格台词或视觉反应承担 punchline。

## 7. Prompt Compiler blocks

### Style core

- finished classic newspaper comic-strip panel
- simple but professionally designed characters
- clean readable black outlines
- light flat colors and uncluttered staging
- clear gag timing and warm everyday observation

### Character block

- distinct silhouettes and repeatable facial features
- expressive hands, posture and reaction without stick-figure anatomy

### Environment block

- consistent recurring location with only essential background objects
- small-panel readability

### Camera block

- clear setup, change and reaction
- one readable action per panel

### Avoid block

- stick figures
- random icon people
- detailed cinematic painting
- crowded background
- identical pose every panel
- unresolved gag
- embedded text

Prompt 编译时只注入本格出场人物、当前场景、当前道具和当前镜头，不能把整套角色表重复塞入每一格。

## 8. 风格签名与硬失败

### 必须看见

- 小尺寸可读
- 角色反差稳定
- 每格有变化
- 最后一格有落点
- 背景不抢戏

### 直接失败并重生成

- 火柴人
- 四格重复同姿势
- 笑点只能靠大段旁白解释
- 人物无法区分
- 场景每格变化

## 9. 研究依据

本风格主要参考：S16, S17, S05。完整链接和用途见根目录 `SOURCES.md`。
