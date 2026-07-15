# 韩漫 / Webtoon-Manhwa — 精修全彩纵向漫画

## 1. 风格定义

- **稳定 ID**：`webtoon-manhwa`
- **生产名称**：Polished Vertical Webtoon
- **传统**：Korean digital comics
- **格式**：mobile-first vertical scroll
- **媒介**：full-color digital line + gradient
- **边界说明**：Webtoon 首先是阅读和版式体系，不是单一脸型。

## 2. 适用范围

**最适合**：手机竖滑；人物关系；都市故事；情绪递进；连续剧情；年轻受众。

**不优先**：严格黑白印刷；必须在一页同时呈现大量并列信息。

**内置子风格**：`romance-polished`, `romance-fantasy`, `urban-drama`, `action-cinematic`, `thriller-horror-scroll`, `slice-of-life-soft-color`, `campus-office-drama`。

完整适用/排除规则见 `../02_SUBSTYLE_CATALOG.md`。

**交付平台**：`vertical-scroll`, `card`, `mobile`。

## 3. 人物设计

- **真实度**：0.64
- **人体**：偏修长但结构可信；避免过长四肢、过小头和统一模特体型。
- **面部**：精修、清洁、易在手机小屏识别；主要角色的眉眼、鼻口、发型轮廓必须区分。
- **形状与轮廓**：人物剪影优先，服装层级简化，重点细节集中在头发、外套和标志性配件。
- **角色生产规则**：细节量适合周更重复生产；表情在手机尺寸仍清楚；避免所有人物同脸。

人物参考板必须包含：正面、3/4、侧面、背面、全身比例、三种核心表情、两种常用手势、标志道具和不可变化项。

## 4. 线条、黑白与色彩

- **线条**：清洁锐利的数字线稿，外轮廓比内部线略重；允许柔和无描边区域，但不能全部变成厚涂。
- **黑白/明度**：用局部深色和环境光建立层次，避免全局高曝光和皮肤塑料感。
- **颜色**：全彩；角色局部色稳定；场景使用渐变和色温过渡；每一幕有明确情绪色。
- **光线**：柔和主光配局部高光；高潮可提高对比；纵向长镜头可用光线渐变连接空间或时间。
- **纹理**：数字完成度高但保留少量材质差异；皮肤、头发、布料、金属不能用同一种光泽。

## 5. 场景与物件

- **场景**：反复场景需锁定平面关系；建立镜头和纵向揭示可较详细，近景背景可降密度。
- **道具**：道具外形清楚、颜色稳定，适合在竖屏近景中快速识别。

反复地点必须建立平面关系和视觉锚点；关键道具必须记录尺寸、轮廓、材料、所有者、使用方式和剧情状态。

## 6. 镜头、分格与字艺

- **镜头**：利用纵向落差、上下视线和滚动揭示；动作方向优先纵向或对角线。
- **分格**：留白是时间和情绪工具；近距离格加快节奏，长空白和长格用于转场、悬念、坠落或空间扩展。
- **字艺**：手机可读字号；气泡沿纵向阅读流交错布置；避免一屏塞入过多文字。

## 7. Prompt Compiler blocks

### Style core

- finished polished Korean vertical-webtoon panel
- clean crisp digital line art
- refined full-color rendering with controlled soft gradients
- mobile-readable faces and silhouettes
- cinematic vertical staging

### Character block

- repeatable costume design and distinct face geometry
- natural hands and elegant but believable anatomy

### Environment block

- consistent recurring environment layout
- selective detail with clear depth layers and mobile-scale focal hierarchy

### Camera block

- composition designed for vertical scroll reveal
- strong top-to-bottom eye flow and readable emotional beat

### Avoid block

- generic beauty-filter faces
- plastic 3D skin
- overlong limbs
- same glossy material on every surface
- horizontal page collage
- embedded text

Prompt 编译时只注入本格出场人物、当前场景、当前道具和当前镜头，不能把整套角色表重复塞入每一格。

## 8. 风格签名与硬失败

### 必须看见

- 纵向阅读流
- 全彩但受控
- 手机尺寸表情清楚
- 留白参与节奏
- 角色不撞脸

### 直接失败并重生成

- 把普通横页直接裁成长图
- 小屏无法辨认动作
- 全员同脸
- 背景每格重置
- 服装颜色漂移
- 光泽塑料化

## 9. 研究依据

本风格主要参考：S05, S06, S10, S11, S12。完整链接和用途见根目录 `SOURCES.md`。
