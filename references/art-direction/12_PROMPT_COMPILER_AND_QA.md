# Prompt Compiler 与自动视觉 QA

## 1. 当前错误模式

现有代码把所有角色和整段 style prompt 放入每一个 panel prompt。这会导致：

- 不出场角色被画进当前格；
- Prompt 变长、主次不清；
- 构图控制下降；
- 同一批负面规则反复冲突；
- 人物、场景、道具和镜头无法独立检查。

## 2. Prompt IR

每格先生成中间表示：

```json
{
  "style_id": "manga",
  "variant_id": "gekiga-cinematic",
  "characters_present": ["c01", "c02"],
  "environment_id": "e03",
  "prop_states": [{"prop_id": "p01", "state": "opened"}],
  "shot": {},
  "action": "",
  "emotion": "",
  "continuity": {},
  "lettering_safe_zone": "top-left",
  "output": {"aspect_ratio": "4:5", "text_free": true}
}
```

## 3. 编译顺序

```text
1. production intent
2. style core
3. active character identity
4. current environment
5. current prop states
6. shot and composition
7. action and emotion
8. focus, light and material logic
9. continuity
10. text-free and safe-zone rules
11. concise avoid block
12. output specification
```

### Production intent

使用明确动词：

```text
Draw a finished production-quality comic panel.
```

不要只写一串风格名词。

### Style core

来自 `nine_styles.json`，每格只使用 4–6 条最核心签名。

### Character block

只注入本格出场角色；身份参考和不可变化项优先于性格形容词。

### Environment block

只注入当前地点的固定锚点、材料、时间、天气和当前光源。

### Prop block

明确当前状态和手部交互，不要只写“一个旧物”。

### Camera block

写具体景别、机位、焦点、前中后景和动作方向。

### Focus, light and material block

写清：

- 3 秒内最先看到什么；
- 主光方向和环境光颜色；
- 关键材质词；
- 哪些细节要压低，避免抢主体；
- 本格是否承担 emotion anchor shot。

不要写空泛的 `beautiful`, `premium`, `highly detailed`。把它们翻译成焦点、光源、材质、边缘、纹理和留白。

### Avoid block

只保留高风险错误：

- style drift；
- identity drift；
- anatomy failure；
- embedded text；
- wrong prop state；
- style-specific hard failures。

不要堆几十条互相重复的 `not`。

## 4. Reference Strategy

图像模型支持多图参考和高保真输入，但仍可能在跨代生成中出现一致性和构图偏差。[S23]

推荐：

1. 先生成并锁定 style proof；
2. 生成角色转面和表情板；
3. 生成环境建立板；
4. 生成关键道具板；
5. 每格使用当前需要的参考；
6. 优先编辑已锁定图，而不是每格从零抽样。

## 5. QA Rubric

每个维度使用 0/1/2：

- 0：失败，必须重生成；
- 1：有明显问题，允许一次修正；
- 2：通过。

### 通用维度

```text
style_signature
substyle_signature
character_identity
anatomy_and_hands
environment_continuity
prop_accuracy
composition_readability
3_second_focus
silhouette_readability
light_material_logic
emotion_anchor
shot_variety
text_contamination
lettering_safe_zone
final_finish
```

### 硬门禁

以下任何一项为 0 都不能入库：

- 角色身份；
- 人体和手；
- 关键道具状态；
- 伪文字；
- 风格漂移；
- 正式完成度。
- 主体、动作和关键道具在手机缩略尺寸下不可读。

### 风格专属 QA

每个风格的 `qa.signature` 和 `qa.hard_fail` 来自 `nine_styles.json`。所选 `variant_id` 对应的 `substyles[].qa_focus` 也必须进入 QA，用于检查该子风格是否真的可见。例如：

- Manga：三值、墨线、网点、镜头节奏；
- Webtoon：纵向流、手机表情、全彩材质；
- Doodle：完整简化人体，禁止火柴人；
- Retro Halftone：网点有密度变化，禁止全屏滤镜；
- Ligne Claire：清楚轮廓、低排线、背景精确；
- Ink Sketch：排线方向服从体积和材质。

## 6. 自动重试

```text
first generation
→ QA
→ targeted repair prompt
→ second QA
→ one final regeneration
→ fail task if still below gate
```

修复提示必须针对失败维度，不要把原 Prompt 原样重跑。

## 7. 记录

每张正式图记录：

```text
style_id / variant_id
prompt_ir
compiled_prompt
reference_asset_ids
provider / model
created_at
qa_scores
retry_reason
accepted_asset_path
sha256
```

这样后续才能追踪“为什么这一格风格漂移”，而不是只看最终 PNG。
