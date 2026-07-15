# 手绘 Doodle — 受控的不完美笔记漫画

## 1. 风格定义

- **稳定 ID**：`doodle`
- **生产名称**：Controlled Hand-Drawn Doodle
- **传统**：notebook doodle and hand-drawn visual notes
- **格式**：card, note-comic, short sequence
- **媒介**：loose pen + flat accent
- **边界说明**：Doodle 的目标是有意的松弛和人味，不是低水平、火柴人或未完成草稿。

## 2. 适用范围

**最适合**：生活方式；心理与自我成长；读书笔记；亲切解释；小红书；轻量人物故事。

**不优先**：需要写实战争、宏大历史空间、复杂动作和高端产品精确展示。

**内置子风格**：`sketchnote-visual-notes`, `notebook-warm`, `marker-color`, `annotated-knowledge`, `diary-comic`, `whiteboard-explainer`, `zine-diy`。

完整适用/排除规则见 `../02_SUBSTYLE_CATALOG.md`。

**交付平台**：`card`, `social`, `notes`, `article`。

## 3. 人物设计

- **真实度**：0.25
- **人体**：简化但完整；头、躯干、四肢和手势需要结构，不允许线条火柴人。
- **面部**：极简五官但角色差异清楚；表情依赖眉、眼、口和头部倾斜。
- **形状与轮廓**：圆润、亲和、符号化；形状可不规则但必须一致。
- **角色生产规则**：轮廓和服装符号重复稳定；情绪真实亲近，不默认儿童。

人物参考板必须包含：正面、3/4、侧面、背面、全身比例、三种核心表情、两种常用手势、标志道具和不可变化项。

## 4. 线条、黑白与色彩

- **线条**：自由手绘、轻微抖动、粗细和收笔变化；重复元素相似但不机械复制。
- **黑白/明度**：大量留白；少量黑色或深色强调；不做均匀灰雾。
- **颜色**：1–4 个柔和或明快强调色；允许轻微出线和马克笔叠色。
- **光线**：通常不做复杂写实光影；用简单投影、色块或纹理说明层次。
- **纹理**：纸张、铅笔、钢笔、马克笔触感；纹理要轻，文字区域保持清楚。

## 5. 场景与物件

- **场景**：用少量家具、植物、窗、桌面和图标提示地点；保持视觉呼吸。
- **道具**：以轮廓和一两个识别细节说明；可配箭头、星号、圈线等视觉注记，但文字后期添加。

反复地点必须建立平面关系和视觉锚点；关键道具必须记录尺寸、轮廓、材料、所有者、使用方式和剧情状态。

## 6. 镜头、分格与字艺

- **镜头**：正面、中景、俯视桌面和小特写组合；构图像精心整理的手账而非随机涂鸦。
- **分格**：卡片或松散格；可用手画边框，但阅读顺序明确。
- **字艺**：可使用手写感字体和手绘容器，但正文必须后期排版，保证可读性。

## 7. Prompt Compiler blocks

### Style core

- finished controlled hand-drawn doodle comic illustration
- organic variable pen lines and intentional imperfections
- simple complete character anatomy, not stick figures
- warm notebook texture with a few flat color accents
- clear visual hierarchy and human charm

### Character block

- recognizable silhouette, stable clothing symbols and expressive posture
- minimal facial marks but distinct identity

### Environment block

- sparse but meaningful everyday objects
- generous breathing room and balanced clusters

### Camera block

- friendly close or medium composition
- organized visual-note rhythm rather than random scribbles

### Avoid block

- stick figures
- childlike crayon art
- illegible messy scribbles
- generic vector icons
- mechanically perfect line
- fake handwriting or embedded pseudo-text

Prompt 编译时只注入本格出场人物、当前场景、当前道具和当前镜头，不能把整套角色表重复塞入每一格。

## 8. 风格签名与硬失败

### 必须看见

- 线条有手感
- 简化但完整的人体
- 留白充足
- 色彩少而准
- 亲切而非幼稚

### 直接失败并重生成

- 火柴人
- 杂乱不可读
- 像低清草稿
- 所有角色只是圆头线身
- 文字伪影
- 机械矢量图标感

## 9. 研究依据

本风格主要参考：S19, S05, S07, S08。完整链接和用途见根目录 `SOURCES.md`。
