# 美式漫画研究附录：不改变九大顶层风格

## 结论

“American comic style”不是单一风格。至少包含：

1. Golden-age pulp：厚墨线、有限色、强封面构图；
2. Silver-age kinetic：英雄比例、速度线、动态透视、明亮色；
3. Bronze-age grounded：更成熟的人物、城市现实和复杂阴影；
4. Modern cinematic：写实解剖、电影镜头、变量刷墨和数字上色；
5. Noir crime：大片实黑、硬光、城市犯罪空间；
6. Indie literary：个性线条、生活化人物、克制表演；
7. Newspaper strip：连续短格、角色关系和节奏；
8. Retro romance/horror：复古印刷色、夸张情绪和网点。

当前九大风格只直接覆盖其中一部分：

| 美式方向 | 当前承载方式 |
|---|---|
| Golden pulp | `retro-halftone / american-golden-pulp` |
| Silver kinetic | `retro-halftone / american-golden-pulp` 或 `manga / shonen-kinetic` 加 modifier |
| Noir crime | `retro-halftone / noir-pulp-cover` 或 `ink-sketch / crosshatch-noir` 加 modifier |
| Indie literary | `editorial / literary-graphic-essay` 或 `ink-sketch / literary-pen` 加 modifier |
| Newspaper strip | `comic-strip / daily-bw` 或 `comic-strip / continuity-story` |
| Retro romance/horror | `retro-halftone / retro-romance-horror` |
| Modern cinematic | 目前只能作为研究型 modifier；若高频使用，应正式新增顶层风格 |

## 为什么不直接新增第十个 ID

用户当前产品已经固定九大风格。本包先保证兼容，不擅自增加菜单项。`presets/american_modifiers.json` 保存美式风格 DNA，Codex 可以实现 modifier 机制，但不得把 modifier 当作顶层 `style_id`。

## 兼容实现

```text
style_id = retro-halftone
variant_id = american-golden-pulp
modifier_ids = []
```

或：

```text
style_id = ink-sketch
variant_id = crosshatch-noir
modifier_ids = [american-noir-crime]
```

## Modern Cinematic 的警告

现代电影化美式图像小说在人物比例、墨线、色彩和镜头上已经形成独立系统。长期把它塞进 `retro-halftone` 或 `ink-sketch` 会再次造成分类错误。若后续用户数据证明需求高，正确动作是：

```text
新增正式 style_id
更新迁移和菜单
而不是用隐藏 prompt 覆盖现有风格语义
```

## 通用美式视觉 DNA

- variable brush-ink line weight；
- clear spotted blacks；
- grounded anatomy with controlled exaggeration；
- strong silhouette and foreshortening；
- foreground/midground/background layering；
- limited narrative palette；
- cinematic shot progression；
- graphic shadow shapes；
- readable action and reaction；
- post-production lettering with balloons and SFX。

这组 DNA 可作为研究参考，但不能让九种风格都变成同一种美式厚涂。
