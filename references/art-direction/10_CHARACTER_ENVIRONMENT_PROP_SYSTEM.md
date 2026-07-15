# 人物、场景与物件统一设计规范

## 1. Character Bible

每个主要角色至少包含：

```text
character_id
narrative_role
age / culture / occupation / body type
primary_shape / secondary_shape
silhouette_markers
height_ratio / body_mass / posture
face_geometry
hair_mass
costume_layers
materials
color_ownership
expression_range
gesture_language
signature_props
immutable_traits
allowed_state_changes
```

### 轮廓测试

把角色全部涂黑并缩小到 5%：

- 主要角色是否仍能区分；
- 头部、肩部、外套、发型和道具是否形成不同轮廓；
- 角色是否只能靠衣服颜色区分；
- 坐、站、背影和远景是否仍能识别。

强轮廓和形状语言是角色可识别性的重要基础。[S08]

### 面部几何

不要使用“英俊、漂亮、疲惫”作为唯一描述。至少定义：

- 脸长宽比；
- 下颌形状；
- 眉毛角度和厚度；
- 眼裂形状和间距；
- 鼻梁和鼻尖；
- 嘴唇厚度和嘴角基线；
- 发际线；
- 年龄纹理和非对称特征。

### 服装与材质

角色设定不只是颜色：

```text
base layer
middle layer
outer layer
footwear
accessories
fasteners
fabric weight
surface wear
movement behavior
```

服装、配件、面部和身体表达共同传递角色人格。[S07]

## 2. Environment Bible

每个反复出现地点至少包含：

```text
environment_id
story_function
region / era / climate
floor_plan
entrances / windows / vertical circulation
fixed_anchors
movable_objects
materials
wear_patterns
light_sources
time_states
weather_states
shot-specific_detail_levels
forbidden_inconsistencies
```

### 场景锚点

一个地点至少锁定 3–5 个不会静默移动的锚点，例如：

- 窗在书桌左侧；
- 门位于后墙右侧；
- 壁炉和书架相对；
- 车站钟、柱列和售票口位置；
- 街角招牌、台阶和路灯关系。

### 细节分配

- 建立镜头：详细；
- 中景对话：保留锚点；
- 情绪近景：简化；
- 道具特写：背景只提供位置语境；
- 动作格：线条和物件沿动作方向组织。

背景可以表达人物是整洁还是凌乱、城市是拥挤还是开阔，并通过固定布局保持连续性。[S05]

## 3. Prop Bible

关键道具使用五层定义：

```text
Story      剧情作用
Ownership  属于谁
Function   如何使用
Form       轮廓、结构、尺寸
Material   材料、磨损、反光与声音
```

再加入：

- `states`：密封、开启、破损、耗尽、污染等；
- `interaction`：单手、双手、佩戴、悬挂、插入、展开；
- `continuity`：前一格和后一格的位置与状态；
- `closeup_features`：特写时必须保留的细节。

## 4. Material Language

不要让所有材质拥有相同的高光和纹理：

- 皮肤：柔和、局部高光、细微色温；
- 头发：按大束组织，不画成塑料丝；
- 棉麻：漫反射、柔软褶皱；
- 羊毛：厚、吸光、边缘略软；
- 皮革：局部硬高光、折痕和磨损；
- 金属：高对比反射、边缘高光；
- 玻璃：透明、反射和折射关系；
- 木：纹理沿构造方向；
- 纸：低反光、边缘和折痕；
- 石：颗粒、裂纹和重量感。

## 5. 跨风格限制

不同风格可以改变表现方法，但不能改变世界事实：

- 角色年龄、肤色、体型、物种和时代；
- 场景平面关系；
- 道具结构和状态；
- 服装层级；
- 角色与道具的所有权。

风格是视觉语言，不是重写原作事实的许可证。
