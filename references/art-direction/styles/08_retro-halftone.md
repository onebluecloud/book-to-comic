# 复古半调漫画 / Retro Halftone — 美式印刷冲击力

## 1. 风格定义

- **稳定 ID**：`retro-halftone`
- **生产名称**：American Retro Print Comic
- **传统**：American pulp / romance / horror / pop-print comic language
- **格式**：page, cover, impact card
- **媒介**：bold ink + limited print palette + Ben-Day/halftone texture
- **边界说明**：半调是印刷与明暗技术；本预设用完整的复古印刷系统承载它。

## 2. 适用范围

**最适合**：封面；强钩子；观点对抗；戏剧冲突；讽刺；复古主题；高能转折。

**不优先**：需要安静微妙、长篇自然主义表演的章节。

**内置子风格**：`benday-pop-print`, `american-golden-pulp`, `retro-romance-horror`, `pop-poster`, `noir-pulp-cover`, `war-propaganda-print`, `cmyk-misregister`。

完整适用/排除规则见 `../02_SUBSTYLE_CATALOG.md`。

**交付平台**：`cover`, `card`, `page`, `poster`。

## 3. 人物设计

- **真实度**：0.62
- **人体**：结构可信、轮廓有力量；可适度夸张姿态和表情，但避免廉价超级英雄 Cosplay。
- **面部**：强眉眼、清楚鼻口、戏剧性表情；保留年龄和个体特征。
- **形状与轮廓**：对角线、爆发形、强轮廓和前后层次；大形优先。
- **角色生产规则**：姿态有冲击力；服装和道具时代一致；角色不是默认超级英雄。

人物参考板必须包含：正面、3/4、侧面、背面、全身比例、三种核心表情、两种常用手势、标志道具和不可变化项。

## 4. 线条、黑白与色彩

- **线条**：粗重刷墨轮廓、局部细线和少量排线；黑块分布明确。
- **黑白/明度**：高对比；纸白、实黑、网点中间调；网点密度随体积和焦点变化。
- **颜色**：有限 CMYK 感色板，通常 3–6 色；高饱和但不使用全光谱霓虹。
- **光线**：硬边戏剧光、轮廓光、舞台式强调；投影形状图形化。
- **纹理**：Ben-Day dots、纸张颗粒、轻微套色偏移和印刷磨损；不能覆盖眼睛、嘴和关键手势。

## 5. 场景与物件

- **场景**：背景可简化成图形化城市、室内或爆发形，但必须提供故事语境。
- **道具**：轮廓大、材质清楚、年代准确；关键道具可作为前景放大。

反复地点必须建立平面关系和视觉锚点；关键道具必须记录尺寸、轮廓、材料、所有者、使用方式和剧情状态。

## 6. 镜头、分格与字艺

- **镜头**：低机位、斜角、极近特写和强透视可增加冲击；仍需控制畸变。
- **分格**：重点格可越框或使用爆发边形；普通格保持阅读秩序。
- **字艺**：后期使用粗体标题、爆发气泡和拟声词；文字不能由图像模型生成。

## 7. Prompt Compiler blocks

### Style core

- finished American retro printed comic panel
- bold brush-ink outlines and deliberate spotted blacks
- limited punchy CMYK-like palette
- selective Ben-Day halftone shading and subtle aged paper grain
- dramatic graphic composition with period-print impact

### Character block

- grounded anatomy with controlled dramatic exaggeration
- distinct face, age, clothing and role, not generic superhero cosplay

### Environment block

- graphic but story-specific setting
- clear period objects and readable silhouette layers

### Camera block

- dynamic diagonal or low-angle composition with one dominant action
- controlled foreshortening

### Avoid block

- modern glossy 3D
- halftone dots uniformly covering every surface
- rainbow palette
- generic superhero costume
- perfect digital gradients
- embedded text

Prompt 编译时只注入本格出场人物、当前场景、当前道具和当前镜头，不能把整套角色表重复塞入每一格。

## 8. 风格签名与硬失败

### 必须看见

- 有限色
- 实黑有设计
- 网点有密度变化
- 印刷质感轻而可信
- 构图冲击力强

### 直接失败并重生成

- 只加网点滤镜
- 所有脸被点阵破坏
- 色彩超过控制范围
- 变成现代 3D 海报
- 角色默认超级英雄
- 套色偏移过重

## 9. 研究依据

本风格主要参考：S20, S16, S06。完整链接和用途见根目录 `SOURCES.md`。
