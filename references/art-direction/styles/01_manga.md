# 日漫 / Manga — 电影化黑白漫画

## 1. 风格定义

- **稳定 ID**：`manga`
- **生产名称**：Manga Cinematic B&W
- **传统**：Japanese manga
- **格式**：page-based sequential art
- **媒介**：digital ink + screentone
- **边界说明**：Manga 是巨大谱系；本预设锁定为适合自动化改编的电影化黑白默认值。

## 2. 适用范围

**最适合**：强情绪；人物冲突；心理机制拟人化；动作与反应；文学戏剧场景。

**不优先**：主要依赖复杂彩色信息图的内容；需要真实品牌或产品颜色的内容。

**内置子风格**：`gekiga-cinematic`, `shonen-kinetic`, `shojo-romance`, `josei-everyday`, `classic-screentone`, `yonkoma-gag`, `chibi-sd-comic`。

完整适用/排除规则见 `../02_SUBSTYLE_CATALOG.md`。

**交付平台**：`page`, `card`, `pdf`, `cbz`。

## 3. 人物设计

- **真实度**：0.58
- **人体**：可信的人体结构，允许情绪和动作夸张；禁止统一幼态脸和通用动漫体型。
- **面部**：为每个角色锁定脸型、眼型、鼻梁、下颌、发际线和年龄特征；眼睛大小由子变体控制。
- **形状与轮廓**：角色轮廓对比明确；主角、对手和导师分别使用不同主形状。
- **角色生产规则**：表情范围大但结构稳定；手势和身体重心必须清楚；服装细节可重复绘制。

人物参考板必须包含：正面、3/4、侧面、背面、全身比例、三种核心表情、两种常用手势、标志道具和不可变化项。

## 4. 线条、黑白与色彩

- **线条**：有压力变化的 G-pen/brush-pen 墨线；受光侧细、背光侧粗；内部结构线比外轮廓轻。
- **黑白/明度**：三值优先：纸白、网点中间调、实黑；大黑块用于构图和焦点，不把整格涂暗。
- **颜色**：默认纯黑白；封面或章节转折可有单一强调色，但正文不依赖彩色。
- **光线**：用黑白分组表现动机光；强烈情绪可使用逆光、轮廓光和抽象背景。
- **纹理**：网点、速度线、集中线、手绘排线按叙事需要使用，不能全画面均匀覆盖。

## 5. 场景与物件

- **场景**：建立镜头详细，反应镜头适度简化；透视准确，场景锚点跨格保持。
- **道具**：以清晰线稿、轮廓和少量排线说明材质；关键道具必须有状态变化。

反复地点必须建立平面关系和视觉锚点；关键道具必须记录尺寸、轮廓、材料、所有者、使用方式和剧情状态。

## 6. 镜头、分格与字艺

- **镜头**：近景和大特写比例较高；动作采用预备—动作—反应；避免八格全是中景。
- **分格**：允许不规则格、斜切和越框，但阅读顺序必须清楚；中文交付默认左到右，除非用户明确要求日式右到左。
- **字艺**：正文后期叠加；对话气泡、内心旁白、拟声词分层；拟声词可成为构图元素。

## 7. Prompt Compiler blocks

### Style core

- finished cinematic black-and-white manga panel
- expressive variable-weight brush-pen line art
- clear silhouettes and controlled anatomy
- three-value design: white paper, screentone midtones, spotted blacks
- selective screentone and hatching, not uniform gray painting

### Character block

- preserve exact face geometry, age, hairstyle masses, costume layers and body proportions
- express emotion through eyes, mouth corners, shoulders, hands and center of gravity

### Environment block

- accurate perspective and recurring location anchors
- detailed establishing space, simplified background where emotion is the focal point

### Camera block

- cinematic shot with a single clear focal point
- readable action and reaction, controlled foreshortening

### Avoid block

- generic anime key visual
- 3D render
- gray digital painting without ink language
- identical medium shot in every panel
- random speed lines
- embedded readable text

Prompt 编译时只注入本格出场人物、当前场景、当前道具和当前镜头，不能把整套角色表重复塞入每一格。

## 8. 风格签名与硬失败

### 必须看见

- 墨线粗细变化
- 三值清楚
- 网点有功能
- 角色轮廓可识别
- 镜头节奏明显

### 直接失败并重生成

- 角色变成通用动漫脸
- 无墨线的灰色插画
- 连续多格同一机位
- 场景透视崩坏
- 手脚畸形
- 图片中出现乱码文字

## 9. 研究依据

本风格主要参考：S01, S02, S03, S05, S06, S25。完整链接和用途见根目录 `SOURCES.md`。
