# 法比漫画 / Franco-Belgian BD — 清线欧洲册页

## 1. 风格定义

- **稳定 ID**：`franco-belgian-bd`
- **生产名称**：Ligne Claire European Album
- **传统**：Franco-Belgian bande dessinée
- **格式**：album/page
- **媒介**：clean ink + flat color
- **边界说明**：当前默认锁定 ligne claire，但不得把整个 BD 传统简化成圆头点眼。

## 2. 适用范围

**最适合**：社科和历史；观点解释；旅行与冒险；复杂场景；需要高级、清楚、耐读的内容。

**不优先**：依赖极端暗黑厚涂或高频动作爆发的场景。

**内置子风格**：`brussels-clear-line`, `marcinelle-comic-dynamic`, `atom-style-retro-modern`, `realistic-adventure`, `semi-realistic-travel`, `big-nose-humor`, `watercolor-album`。

完整适用/排除规则见 `../02_SUBSTYLE_CATALOG.md`。

**交付平台**：`page`, `pdf`, `card`, `album`。

## 3. 人物设计

- **真实度**：0.55
- **人体**：角色可简化或半写实，但比例稳定、动作清楚；不强制圆头点眼。
- **面部**：五官简洁、识别性高，表情依赖眉眼、嘴型和姿态；不同年龄和职业必须区分。
- **形状与轮廓**：清楚、几何、轮廓稳定；人物简化与相对真实的环境形成可读对比。
- **角色生产规则**：表演清楚、姿态可读、重复绘制稳定；服装结构比装饰细节更重要。

人物参考板必须包含：正面、3/4、侧面、背面、全身比例、三种核心表情、两种常用手势、标志道具和不可变化项。

## 4. 线条、黑白与色彩

- **线条**：清晰黑色轮廓，粗细变化有限且有纪律；少排线或无排线；所有重要物体都有可读边界。
- **黑白/明度**：不依赖大片渐变阴影；通过轮廓、局部固有色、少量投影和构图分组建立层次。
- **颜色**：暖而清楚的平涂色；有限阴影；相邻色块需有足够区分。
- **光线**：光源明确但处理简洁；阴影形状干净，避免写实渲染淹没线条。
- **纹理**：低纹理；材料主要靠形状、局部线和颜色表达。

## 5. 场景与物件

- **场景**：背景精确、透视可读、道路建筑家具关系清楚； recurring location 建立平面图。
- **道具**：机械、交通工具、器物和家具可有工程式清晰度；关键道具轮廓要准确。

反复地点必须建立平面关系和视觉锚点；关键道具必须记录尺寸、轮廓、材料、所有者、使用方式和剧情状态。

## 6. 镜头、分格与字艺

- **镜头**：以 35–50mm 的可读空间为主，穿插道具特写和反应近景；不过度使用景深模糊。
- **分格**：规则格与适度变化；每格信息完整；动作连续性清楚。
- **字艺**：清洁气泡和旁白框；字体中性、可读；气泡不遮挡精确背景中的关键线索。

## 7. Prompt Compiler blocks

### Style core

- finished Franco-Belgian album comic panel
- disciplined ligne-claire ink contours
- precise readable environments
- warm controlled flat colors with minimal shading
- clear acting and elegant visual storytelling

### Character block

- stable stylized proportions and distinct silhouettes
- simple but specific faces, not generic round-headed mascots

### Environment block

- accurate perspective, architecture and object placement
- foreground, midground and background remain readable without blur

### Camera block

- clear 35mm-to-50mm staging with readable spatial relationships
- one focused narrative beat

### Avoid block

- anime face language
- painterly concept art
- heavy cross-hatching
- cinematic depth-of-field blur
- overly childish dot-eye characters
- embedded text

Prompt 编译时只注入本格出场人物、当前场景、当前道具和当前镜头，不能把整套角色表重复塞入每一格。

## 8. 风格签名与硬失败

### 必须看见

- 清楚轮廓
- 低排线
- 平涂色
- 背景精确
- 空间关系一眼可读

### 直接失败并重生成

- 把 BD 固定成幼儿圆头
- 背景模糊或随意
- 厚涂油画感
- 阴影过重
- 线条粗细无纪律
- 复杂环境透视错误

## 9. 研究依据

本风格主要参考：S15, S05, S24。完整链接和用途见根目录 `SOURCES.md`。
