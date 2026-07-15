# 国漫 / Manhua — 现代中文全彩漫画

## 1. 风格定义

- **稳定 ID**：`manhua`
- **生产名称**：Modern Chinese Full-Color Manhua
- **传统**：Chinese comics / manhua
- **格式**：digital page or vertical social comic
- **媒介**：full-color digital line with optional painterly or ink accents
- **边界说明**：不能把国漫等同于仙侠、古风或游戏概念图；文化与时代由书籍内容决定。

## 2. 适用范围

**最适合**：中文社媒；都市与历史；中国文化内容；现实题材；人物剧情；全彩知识叙事。

**不优先**：明确要求纯黑白日漫语法的项目。

**内置子风格**：`modern-urban`, `historical-elegant`, `wuxia-action`, `xianxia-fantasy`, `ink-accented`, `lianhuanhua-retro`, `social-realism`。

完整适用/排除规则见 `../02_SUBSTYLE_CATALOG.md`。

**交付平台**：`card`, `vertical-scroll`, `page`, `wechat`。

## 3. 人物设计

- **真实度**：0.66
- **人体**：自然、克制、适合成年人和多年龄角色；不得默认所有角色年轻、纤细、白皙。
- **面部**：依据地域、年代、职业和年龄设计；保留中文读者熟悉的现实细节，而不是统一偶像脸。
- **形状与轮廓**：现代题材强调职业、生活方式和社会身份；历史题材强调轮廓、层叠服装和时代器物。
- **角色生产规则**：姿态克制但表演清楚；服装、发型和配件承担身份信息。

人物参考板必须包含：正面、3/4、侧面、背面、全身比例、三种核心表情、两种常用手势、标志道具和不可变化项。

## 4. 线条、黑白与色彩

- **线条**：清洁但略带绘画感的数字线稿；可有书法式收笔或墨色变化，但不能机械复制水墨符号。
- **黑白/明度**：彩色为主，深浅结构清楚；需要国画气质时使用留白、虚实和墨色层次，而不是加一层水墨滤镜。
- **颜色**：丰富但受控；建立文化与时代色板；古代题材避免影楼式金红满屏，现代题材避免统一霓虹蓝紫。
- **光线**：自然光源与环境色明确；历史室内考虑窗、灯、烛火；现代城市考虑广告光、室内灯和天气。
- **纹理**：丝、棉、麻、木、石、漆、纸、金属等材质需有区分；传统纹样必须与时代和身份相符。

## 5. 场景与物件

- **场景**：文化和地域准确；街道、室内、园林、办公空间不能只做泛亚洲背景。
- **道具**：器物造型、握持方式、书写方向、包装和标识逻辑需符合年代；不生成可读伪文字。

反复地点必须建立平面关系和视觉锚点；关键道具必须记录尺寸、轮廓、材料、所有者、使用方式和剧情状态。

## 6. 镜头、分格与字艺

- **镜头**：兼顾人物情绪与环境叙事；可使用借景、框景、层层推进，但必须服务故事。
- **分格**：页面或竖向均可；中文阅读顺序明确；重要文化细节给道具特写。
- **字艺**：中文标点、行长和字重适配；气泡与旁白后期叠加，避免模型生成汉字。

## 7. Prompt Compiler blocks

### Style core

- finished modern Chinese full-color comic panel
- clean expressive digital linework with restrained painterly accents
- culturally and historically specific design
- rich but controlled color palette
- clear modern sequential storytelling

### Character block

- source-appropriate age, ethnicity, body type, occupation and era
- distinct facial geometry and costume hierarchy

### Environment block

- specific Chinese regional, urban, historical or domestic environment only when supported by the story
- accurate architecture, materials and spatial anchors

### Camera block

- balanced character acting and environmental storytelling
- clear focal hierarchy and readable Chinese social-media composition

### Avoid block

- generic xianxia game art
- automatic hanfu
- whitewashed idol faces
- random dragons, clouds or ink splashes
- fantasy palace for modern scenes
- embedded Chinese pseudo-text

Prompt 编译时只注入本格出场人物、当前场景、当前道具和当前镜头，不能把整套角色表重复塞入每一格。

## 8. 风格签名与硬失败

### 必须看见

- 文化和时代准确
- 全彩不浮艳
- 人物年龄身份明确
- 环境不是泛亚洲
- 材质和器物可信

### 直接失败并重生成

- 现代书被强制古风
- 所有人物同一网红脸
- 服装与年代错位
- 伪汉字
- 背景使用无关宫殿或仙侠元素
- 肤色和体型被统一

## 9. 研究依据

本风格主要参考：S13, S14, S05, S09。完整链接和用途见根目录 `SOURCES.md`。
