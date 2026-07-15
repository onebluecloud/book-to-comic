# 成人编辑漫画 / Editorial — 象征性观点插画

## 1. 风格定义

- **稳定 ID**：`editorial`
- **生产名称**：Adult Symbolic Editorial Cartoon
- **传统**：adult editorial cartoon and illustration
- **格式**：single-panel or short sequence
- **媒介**：economical ink + limited color
- **边界说明**：使用通用编辑漫画语言，不要求模仿某一具体刊物或画家。

## 2. 适用范围

**最适合**：认知和哲学；社会科学；商业观点；成人幽默；抽象概念；一图一喻。

**不优先**：需要复杂动作连续性或奇幻世界大场面的章节。

**内置子风格**：`political-satire`, `symbolic-minimal`, `dry-gag`, `conceptual-texture`, `literary-graphic-essay`, `infographic-explainer`, `surreal-metaphor`。

完整适用/排除规则见 `../02_SUBSTYLE_CATALOG.md`。

**交付平台**：`card`, `article`, `page`, `cover`。

## 3. 人物设计

- **真实度**：0.43
- **人体**：普通成人比例，可有轻微夸张；姿态和手势比肌肉细节重要。
- **面部**：经济线条、少量特征即可识别；讽刺时夸张必须服务观点而非羞辱身份。
- **形状与轮廓**：每格围绕一个主要视觉隐喻；形状关系简明，负空间参与表达。
- **角色生产规则**：角色是观点载体但仍要有生活感；职业、姿态和道具提供社会语境。

人物参考板必须包含：正面、3/4、侧面、背面、全身比例、三种核心表情、两种常用手势、标志道具和不可变化项。

## 4. 线条、黑白与色彩

- **线条**：自信、经济、略带手工感；线条不追求机械完美，也不能变成潦草未完成。
- **黑白/明度**：以留白和少量实线为主；必要时用局部黑块或浅洗染强调。
- **颜色**：2–5 个低饱和色；单一强调色负责概念焦点。
- **光线**：不追求电影写实；用局部投影或色块说明空间即可。
- **纹理**：轻纸纹、浅洗染、有限铅笔或墨水纹理。

## 5. 场景与物件

- **场景**：仅保留理解隐喻所需的场景信息；避免装饰性背景抢夺概念。
- **道具**：道具经常承担隐喻，必须轮廓明确、比例合理、语义单一。

反复地点必须建立平面关系和视觉锚点；关键道具必须记录尺寸、轮廓、材料、所有者、使用方式和剧情状态。

## 6. 镜头、分格与字艺

- **镜头**：正面、侧面或轻微俯视为主；构图像一句精确论证，不追求过度动态。
- **分格**：单格或短序列；每格一个命题；跨格通过同一隐喻递进。
- **字艺**：标题、旁白和对话后期完成；文字短、锋利；不让画面依赖大段解释。

## 7. Prompt Compiler blocks

### Style core

- finished adult editorial cartoon illustration
- economical confident hand-drawn linework
- one strong visual metaphor
- limited muted palette and generous negative space
- sophisticated, dry and concept-first

### Character block

- ordinary adult proportions and observant body language
- specific social role conveyed through posture, clothing and one or two props

### Environment block

- only the environmental information required to understand the metaphor
- clean negative space and uncluttered hierarchy

### Camera block

- simple readable composition like a precise visual argument
- single focal metaphor

### Avoid block

- generic corporate clip-art
- cute mascot style
- over-rendered 3D
- multiple competing metaphors
- visual noise
- direct imitation of a named living artist
- embedded text

Prompt 编译时只注入本格出场人物、当前场景、当前道具和当前镜头，不能把整套角色表重复塞入每一格。

## 8. 风格签名与硬失败

### 必须看见

- 一格一喻
- 线条经济
- 负空间有效
- 色彩克制
- 观点在无文字时仍基本可读

### 直接失败并重生成

- 堆砌多个隐喻
- 变成儿童插画
- 变成扁平企业图库
- 过度渲染
- 没有清楚观点焦点

## 9. 研究依据

本风格主要参考：S18, S19, S16, S05。完整链接和用途见根目录 `SOURCES.md`。
