# 黑白钢笔 / Ink Sketch — 文学性墨线与排线

## 1. 风格定义

- **稳定 ID**：`ink-sketch`
- **生产名称**：Literary Pen-and-Ink
- **传统**：pen-and-ink drawing and literary illustration
- **格式**：page, card, editorial sequence
- **媒介**：ink line + hatching + optional wash
- **边界说明**：必须是完成的墨线作品，不是粗糙草图或灰色素描占位。

## 2. 适用范围

**最适合**：文学；哲学；历史；严肃社科；回忆；心理和象征场景。

**不优先**：高度依赖鲜艳品牌色或轻快偶像感的内容。

**内置子风格**：`crosshatch-noir`, `literary-pen`, `fine-line-portrait`, `travel-journal`, `stipple-texture`, `woodcut-expression`, `ink-wash-muted`。

完整适用/排除规则见 `../02_SUBSTYLE_CATALOG.md`。

**交付平台**：`page`, `pdf`, `card`, `article`。

## 3. 人物设计

- **真实度**：0.72
- **人体**：自然可信，允许通过线条省略细节；面部和手部需准确。
- **面部**：以轮廓、少量结构线和排线塑造年龄与情绪；避免过多细碎线破坏表情。
- **形状与轮廓**：轮廓克制，黑白密度引导焦点；文学场景允许象征性空间。
- **角色生产规则**：细微表情、手势和姿态；衣褶方向说明材料和动作。

人物参考板必须包含：正面、3/4、侧面、背面、全身比例、三种核心表情、两种常用手势、标志道具和不可变化项。

## 4. 线条、黑白与色彩

- **线条**：钢笔、蘸水笔或刷笔质感；线条有方向、压力和节奏；排线顺着体积和材质。
- **黑白/明度**：纸白、线性中间调、局部实黑；可用稀释墨水 wash 形成有限灰阶。
- **颜色**：默认黑白或暖黑/棕黑；可有单一低饱和强调色。
- **光线**：明确光源；通过排线密度、实黑和留白塑造光。
- **纹理**：纸纹、排线、交叉排线、点描和墨洗按材质分配；不能用同一排线覆盖所有物体。

## 5. 场景与物件

- **场景**：透视准确；以线密度区分前中后景；远景简化，焦点区域细化。
- **道具**：结构准确；木、金属、布、玻璃、纸通过不同线条和高光留白表达。

反复地点必须建立平面关系和视觉锚点；关键道具必须记录尺寸、轮廓、材料、所有者、使用方式和剧情状态。

## 6. 镜头、分格与字艺

- **镜头**：安静中景、道具特写、情绪近景和建立镜头交替；避免全篇一个正面机位。
- **分格**：规则格或文学性开放边界；黑白密度在整页形成节奏。
- **字艺**：后期使用克制字体、开放旁白或细线气泡；文字区域保持纸白。

## 7. Prompt Compiler blocks

### Style core

- finished literary pen-and-ink comic illustration
- confident expressive nib lines
- directional hatching and selective cross-hatching that follows form
- clear paper white, line-based midtones and controlled solid blacks
- quiet adult graphic-novel mood

### Character block

- accurate adult anatomy, subtle expression and readable hands
- preserve exact age, face structure, clothing and posture

### Environment block

- accurate perspective with density-based depth
- detailed focal area and simplified distance

### Camera block

- restrained cinematic composition with a clear emotional or symbolic focal point
- varied shot scale

### Avoid block

- unfinished pencil rough
- uniform gray smudge
- photoreal charcoal shading
- same hatch pattern on skin, cloth, wood and metal
- cute manga face
- embedded text

Prompt 编译时只注入本格出场人物、当前场景、当前道具和当前镜头，不能把整套角色表重复塞入每一格。

## 8. 风格签名与硬失败

### 必须看见

- 线条方向服从体积
- 黑白密度有层级
- 材质排线不同
- 作品完成而非草稿
- 留白有效

### 直接失败并重生成

- 像未完成速写
- 排线噪声覆盖脸
- 材质无法区分
- 透视错误
- 灰色涂抹取代线性结构
- 所有格同一密度

## 9. 研究依据

本风格主要参考：S21, S05, S09。完整链接和用途见根目录 `SOURCES.md`。
