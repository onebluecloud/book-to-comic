from textwrap import dedent

from .models import AdaptationPackage, Character, Panel
from .sample_data import thinking_fast_and_slow_ep1
from .styles import get_style


def build_sample_package() -> AdaptationPackage:
    return thinking_fast_and_slow_ep1()


def render_manual_package(package: AdaptationPackage, style_id: str | None = None) -> str:
    style = get_style(style_id or package.style_id)
    lines: list[str] = [
        f"# 样板输出 · {package.episode_title}",
        "",
        "> Legacy prompt-pack export. The default Skill path is host-native: the current Codex/Claude session executes adaptation and uses deterministic scripts for rendering, composition, and delivery.",
        "",
        "## 输入",
        f"- 书：{_book_label(package)}",
        f"- 适用性判断：{'✅' if package.suitability.is_applicable else '❌'} {package.suitability.category} —— {package.suitability.reason}",
        f"- 本话覆盖要点：{_join_items(package.covered_points)}",
        f"- 改编手法：{_join_items(package.methods)}",
        f"- 轻壳硬芯：{package.light_shell}（壳）× {package.hard_core}（芯）",
        "",
        "## 核心观点",
    ]

    for index, idea in enumerate(package.core_ideas, start=1):
        lines.extend(
            [
                f"{index}. **{idea.title}**：{idea.kernel}",
                f"   - 戏剧化：{idea.dramatization}",
            ]
        )

    lines.extend(
        [
            "",
            "## 角色设定表",
        ]
    )
    for character in package.characters:
        lines.append(
            f"- **{character.name}（{character.concept}）**：{character.visual}"
            f" 性格={character.personality}"
        )
    lines.append(f"- 关系：{package.character_relationship}")
    lines.extend(
        [
            "",
            "## 角色指纹（防止逐格漂移）",
            "- 颜色属于服装，不是皮肤；肤色、年龄、体型、族裔和时代背景按原作和角色设定锁定。",
            "- 每格必须引用同一张 reference image；只允许改变动作、表情和场景，不得重新设计角色。",
            "- 如果快脑变成红色皮肤、慢脑丢失眼镜/蓝色开衫、服装或体型改变，质检不过，重生该格。",
            "- English lock: do not redesign the characters; do not change clothing, skin tone, body proportions, face, glasses, or color ownership.",
            "",
            "角色指纹明细：",
        ]
    )
    for character in package.characters:
        lines.append(f"- **{character.name}**：{character.prompt_fragment}")

    lines.extend(
        [
            "",
            f"## {len(package.storyboard)} 格分镜脚本",
        ]
    )
    for panel in package.storyboard:
        lines.append(_render_panel_script(panel))

    lines.extend(
        [
            "",
            "## 标题候选（≤20 字）",
        ]
    )
    for index, title in enumerate(package.title_candidates, start=1):
        lines.append(f"{index}. {title}")

    lines.extend(
        [
            "",
            "## 角色定妆 Prompt",
            "",
            "先用这一条生成 reference image，后续每格 prompt 都引用这张 reference image。",
            "",
            "```text",
            style.prompt_spec,
            "",
            "Scene: character reference sheet for the recurring cast; full-body simple poses,",
            "consistent proportions, neutral background, no speech bubbles.",
        "Lock clothing, skin tone, face, glasses, body proportions, and color ownership.",
        "Pose safety: adult ordinary proportions, natural readable limbs and hands, no warped anatomy, no extreme foreshortening, no mascot proportions.",
        "Colors belong to clothing, not skin. do not redesign the characters.",
        "No readable text, letters, numbers, or pseudo-text.",
            "",
            "Characters:",
            _character_prompt_lines(package.characters),
            "```",
            "",
            "## 逐格图像 Prompt（legacy export）",
            "",
        "这些 prompt 用于需要导出提示词给外部图像流程的兼容场景；宿主原生工作流优先直接调用当前环境图像工具或 vector 兜底。",
        "默认让图片工具不画对白气泡、底部旁白框、结尾留白区、白色标签、价签、卡片、标牌、UI 占位或任何文字预留框。中文台词、旁白和数字后期叠字。",
        ]
    )

    for panel in package.storyboard:
        lines.extend(_render_panel_prompt(panel, package.characters, style.prompt_spec))

    lines.extend(
        [
            "",
            "## 使用备注",
            "- 整本书锁同一套角色定妆 reference image、同一套风格 spec、同一组主色。",
            "- 逐格生成时必须带 reference image 和角色指纹；质检不过就重生该格，不要靠后期修角色。",
            "- 如果换风格，只替换风格 spec；分镜和角色设定不要重写。",
            "- 默认宿主原生链路通过 `extract -> validate -> render -> compose -> export` 产出项目交付物；外部 API 只属于显式启用的独立扩展。",
        ]
    )

    return "\n".join(lines).strip() + "\n"


def build_adaptation_prompt(
    book_title: str,
    author: str = "",
    notes: str = "",
    style_id: str = "editorial",
) -> str:
    style = get_style(style_id)
    author_line = f"作者：{author}" if author else "作者：未知或未提供"
    notes_text = notes.strip() if notes.strip() else "未提供。若你不知道这本书的可靠内容，请先要求用户补充简介、目录或要点，不要编造。"
    notes_block = _indent_multiline(notes_text, "        ")
    style_block = _indent_multiline(style.prompt_spec, "        ")

    prompt = dedent(
        f"""
        # 书变漫画宿主执行任务说明

        你是当前 Codex / Claude Code 会话中的“书变漫画”执行者。你的核心价值是把一本书先拆成章节/篇章/情节段，再把单个 episode 戏剧化成真正连续的漫画脚本。当前宿主模型直接执行研究、理解、改编、分镜、图片工具调用和质检；项目脚本只做确定性提取、校验、vector 渲染、排版和导出。外部 API 只在用户显式启用独立扩展时使用。

        ## 输入
        - 书名：{book_title}
        - {author_line}
        - 用户已有要点 / 想法：
        {notes_block}
        - 目标风格：{style.name}（{style.reference}）

        ## Series-First Structure
        Do not compress a whole book into one 6-8 panel episode.

        改编结构必须是：整本书 -> 篇章 / 章节 / 情节段 -> episode -> panel。

        - 先做全书分话规划：列出主要篇章、章节、剧情节点或概念单元，每一话一句话说明讲什么。
        - EP1 只是第一话，不是整本书浓缩版。
        - 小说 / 文学类也可以做，但要按章节、场景、人物弧光或关键情节段改编，不能把整部小说压成几格解释。
        - 认知、社科、哲学、科普、方法论类按章节观点或核心概念拆话，每话只讲一个局部闭环。
        - 每话必须有漫画弧线：钩子、铺设、冲突、转折、获得感收束；中间话再留悬念。

        ## dynamic panel count
        不再固定 6-8 格。根据剧情和信息量选择格数。

        - 短钩子或简单观点：4-6 panels。
        - 标准移动端轮播一话：6-10 panels。
        - 文学/小说/剧情较重的一话：10-14 panels。
        - hard cap is 16 panels；超过就拆成上下两话。
        - 每一格必须有推进：动作、反应、揭示、选择、后果、情绪转折或视觉节拍。不要为了凑数加格。

        ## Style Menu
        如果用户没有指定风格，先推荐风格菜单，再锁定一个 style_id。

        - 文学经典/严肃随笔：editorial / ink-sketch / franco-belgian-bd。
        - 剧情小说/强戏剧场景：manga / webtoon-manhwa / manhua / franco-belgian-bd。
        - 移动端轻知识/读书笔记：doodle / manhua / webtoon-manhwa。
        - 讽刺、复古、强钩子：retro-halftone / comic-strip。
        - 可用 style_id 只能来自：manga, webtoon-manhwa, manhua, franco-belgian-bd, editorial, comic-strip, doodle, retro-halftone, ink-sketch。

        ## Character Bible Levels
        根据系列长度选择人物定妆深度。

        - 短篇/单话：character fingerprint + 一张 approved character reference image。
        - 短系列：character fingerprint + reference image + 固定道具/服装锁定。
        - 长篇小说/文学系列：character bible，包括 turnaround sheet、expression sheet、服装/道具、关系图、环境锚点。
        - 未完成对应级别定妆前，不要生成正式分镜图。

        ## Comic Image Director
        book-to-comic 内置漫画生图导演模块，不依赖外部通用生图 skill。

        - 先运行 capability detector：检查 host-image、local-model、vector；external-api 只在用户显式启用时使用。
        - 输出 character reference builder：角色指纹、服装、道具、色彩锚点和 approved reference plan。
        - 输出 scene bible builder：每个核心场景的空间布局、光线、时代、关键物件和可变/不可变元素。
        - 输出 panel prompt compiler：每格 prompt 必须引用同一角色/场景设定，并写入 negative prompt。
        - 输出 continuity guard：不得改变肤色、年龄、体型、服装、标志物、画风和关键场景锚点。
        - 输出 visual QA 和 selective rerender：检查角色漂移、乱码文字、空白框、服装变化、场景不连续、肢体崩坏；只重画失败格。
        - 高质量商业插画依赖宿主生图能力或本地图像模型；两者都不可用时，vector 只承诺完整、可读、非空白。
        - 默认不要求 API Key。外部 API 只能作为可选增强写进说明，不得作为默认前提。

        ## Delivery Format Selection
        不要把所有内部工作文件都丢给用户。先让用户选择或根据场景推断交付格式。

        - 默认漫画阅读包：pdf + cbz + epub-fixed-layout + long-png + zip-production。
        - pdf：分页漫画 proof，用于阅读、评审或打印。
        - cbz：按顺序打包图片的漫画阅读器格式。
        - epub-fixed-layout：固定版式漫画电子书，适合导入微信读书、Apple Books、Calibre、ReadEra 等阅读软件尝试阅读。
        - long-png：一张竖版长图，用于预览、公众号或审阅。
        - zip-production：生产交付包，包含公开成品、source JSON、prompts、panels、cards、manifest、review notes。
        - cards：可选单格 PNG 轮播卡片，通常 1080 x 1440；这是排版形态，不是默认漫画交付。
        - panels：可选原始单格图，只在用户明确要二次加工、逐格审图或平台发布时交付。
        - json-source：给后续系统复用或重渲染的结构化源文件。
        - Do not dump internal working files, failed generations, drafts, raw panels, cards, or debug contact sheets unless the user asks.

        ## 0 先判断适用性
        判断这本书适不适合做章节/篇章/情节段漫画系列，还是只适合查表和精确操作。

        - 适合：观点 / 认知型，例如方法论、社科、科普、认知、哲学。
        - 适合：小说、文学经典、历史、传记，只要能按章节、场景、人物弧光或情节段做系列化改编，并且用户接受覆盖部分的剧透。
        - 不适合：工具书 / 参考书，例如编程书、菜谱、操作手册。
        - 不适合：要求逐页复刻整部长篇小说、或不允许剧透但又要讲剧情的任务。

        如果不适合，停止输出漫画方案，只说明不适合的原因和更合适的处理方式。

        ## 1-8 Pipeline
        1 判断适用性：输出是否适合章节/篇章/情节段漫画系列，不适合则中止。
        2 全书分话规划：按章节、篇章、情节节点、人物弧光或概念单元拆成 episode 列表。
        3 选择当前 episode：说明本话覆盖哪一章/哪一段/哪一个概念，不要把整本书压进 EP1。
        4 设置动态格数：按故事需要选择 4-14 panels，16 是硬上限。
        5 提炼本话要点：只选本话需要的观点、剧情因果或人物变化。
        6 选择可视化方法：概念拟人化、案例情景剧、读者代入、观点擂台、或剧情场景改编。
        7 角色设计和定妆级别：根据短篇/短系列/长篇选择 character fingerprint、reference image 或完整 character bible。
        8 分镜和图像执行说明：输出本话分镜、叠字、角色定妆说明、场景锚点、comic-image-director 计划和每格图像说明。若当前环境没有宿主图片工具或本地图像模型，使用 vector 兜底。

        ## 角色一致性硬门
        - 先输出角色指纹：脸/手肤色、服装、鞋、发型或标志物、体型比例、眼镜等固定特征。
        - 颜色属于服装，不是皮肤；不要把“橙红色角色”写成全身红皮肤。
        - 先生成一张角色定妆 reference image；后续每格 prompt 都必须引用同一张 reference image。
        - 如果用户已经认可的定妆图存在，就以那张为唯一标准；不要重新生成、优化、修正或再设计角色。
        - 不允许直接生成单格：没有附上已批准的 00-character-reference 定妆图时，先停止，先生成并批准定妆图。
        - 每格只允许改变动作、表情和场景；不得重新设计角色，不得改变服装、肤色、体型比例、眼镜和徽章。
        - 姿态安全：adult ordinary proportions, natural readable limbs and hands, no warped anatomy, no extreme foreshortening, no mascot proportions。
        - 每格生成后做质检：角色指纹不一致、出现红色皮肤、慢脑丢眼镜、出现乱码文字或数字错误，都算质检不过，重生该格。

        ## 图中文字处理硬门
        - 不要让图片模型直接生成中文台词、旁白、价格、算式、UI 文案、标牌或旗子文字。
        - 不要用空白价签、空白卡片、空白旗子、空白标牌、空白 UI、白色矩形、文字预留框来承载后期文字；这些会让画面显得廉价。
        - 用物体、动作、表情、锚、购物车、货架、印章、灯号和图标表达概念；台词、旁白、价格和评论钩子后期在最终长图排版里统一添加，不放进单格图。
        - 不要画对白气泡；不要画底部旁白框、空白字幕框、大白框或结尾留白区。
        - 每格 prompt 必须写明：no readable text, letters, numbers, prices, equations, or pseudo-text。
        - 把准确台词、旁白、价格和评论钩子单独列成“叠字文本（后期添加，不放进图片 prompt）”。

        ## 叠字文案硬门：语境层 + 翻译层
        - 叠字不是只写“主题升华”。每格必须包含语境层 + 翻译层。
        - 第 1 格必须用大白话交代主角是谁和处境，不要一上来甩人名、术语或抽象概念。
        - 每格遵循“先字面，后主题”：先一句说清画面里发生什么，让没读过书的人也能进入；再给主题升华。
        - 文学、哲学、专业概念必须翻译成日常大白话，例如把“意义饥饿”写成“什么都懂却还是觉得空”，把“灵魂代价”写成“这笔账不会马上写出来”。
        - 翻译不等于变浅：保留深度，但必须讲清楚。
        - 验收：没读过原著的人，只读本话叠字，也能看懂“这是谁、正在发生什么、想讲什么道理”。

        ## 接地气层 / 生活桥
        - 目标受众是移动端社媒的大众读者，包括学生、宝妈、上班族和本来对这本书没兴趣的人。
        - 第 1 格在交代主角是谁和处境之后，必须再搭一个读者生活桥：把书的内核接到当代大众熟悉的生活场景或痛点，让冷读者觉得“这跟我有关”。
        - 关键概念除了翻译成大白话，至少再给一个准确、可辩护的当代生活类比，让读者照见自己。
        - 最后一格收尾要用「收束 + 悬念 + 撩评论」：先把本话核心点讲透，让读者独立看懂并有获得感；再留一句不剧透、指向后续的悬念钩子；最后保留可晒经历、可站队的撩评论问题。
        - 悬念不是半截没讲完：本话主题必须先独立成立，悬念只是额外埋钩。可以用「代价何时来 / 他真的赢了吗 / 后来呢」这类开放收法，但不要剧透下一话。
        - 如果这一话是整本书系列的真正完结篇，只做收束和撩评论，不强行留悬念；中间话都要留钩。
        - 因书制宜：认知、实用、社科、哲学、科普类可以多搭生活桥；文学审美类和氛围型经典要轻一点，靠情绪共鸣和场景平行，不要硬塞刷手机、买东西等现代梗损伤原著质感。
        - 接地气 = 入口亲切，不是内容廉价。禁止低幼化、标题党、震惊体、鸡汤化、贬低读者，禁止把经典做掉价。
        - 生活类比必须准确、可辩护；不能牵强附会，不能为了熟悉感曲解原著。
        - 接地气不等于变浅：生活桥只负责帮读者进入，书的内核和深度不能丢；方向是拉高读者，让读者觉得“我也能读懂经典，还能拿来当谈资”。

        ## 内容密度 / 信息量
        - 叠字不是只留一句金句。每格至少承载三层中的两层：画面事实、心理或因果推进、读者能带走的解释。
        - 当角色冲突、诱惑、误解或选择需要更清楚时，可以加入短台词、心声或提问；这些仍是后期叠字，不让图片模型画对白气泡。
        - 信息量要服务阅读推进：让读者知道这格比上一格多了什么，而不是重复同一个抽象主题。
        - 充实不等于啰嗦：句子具体，删掉重复抽象词，给排版留下呼吸感。

        ## 移动端轮播叠字压缩门：≤3句 / 三层 / 约 40% 压缩
        - 如果最终要发一页一格的轮播卡片，每格叠字最多三句或三段；相对长图 review 版砍掉约 40%，避免像文章解读。
        - 固定三层顺序：一句角色台词（有真实说话人时放） + 一句大白话解释（这格道理是什么） + 一句现实映射（今天的人为什么会遇到）。
        - 没有合适台词时不要硬编，保留两句也可以；但不能超过三句。
        - 中间话最后一格可以把三句用作：收束本话主题 + 不剧透悬念 + 撩评论。若角色台词会导致超过三句，就删掉或并入收束句。
        - 压缩不是变浅：保留语境、因果和深度，删掉重复抽象词、长铺垫和文章式解释。

        ## 视觉舒适硬门
        - 抽象概念可以拟人化，但不要默认使用人体剖面、脑内房间、器官内部空间或令人不适的生理隐喻。
        - 优先使用决策驾驶台、工作室控制台、舞台、办公室、棋盘、商店、桌面或屏幕界面等舒服的日常隐喻。
        - 只有用户明确要求人体/医学/解剖视觉时，才使用相关画面。

        ## 改编铁律
        - 轻壳硬芯：大众日常场景当壳，书里真观点当芯。
        - 每话只讲一个主观点，最多用一个相关偏误或案例辅助。
        - 结尾必须有可站队 / 可晒经历的撩评论钩子。
        - 角色和画风必须整本锁定。
        - 默认输出是漫画阅读包：PDF、CBZ、固定版式 EPUB、长图和 production ZIP；cards 和原始 panels 只作为可选单格导出或 production ZIP 内部资产。
        - 不要把宿主模型包装成 provider，不要从 Python 再启动宿主 CLI；外部 API 只属于显式启用的独立扩展。

        ## 风格 spec
        ```text
        {style_block}
        ```

        ## 必须按这个格式输出
        # 《书名》EP1

        ## 输入
        - 书：
        - 适用性判断：
        - 全书分话规划：
        - 本话覆盖章节/篇章/情节段：
        - 本话覆盖要点：
        - 改编手法：
        - 轻壳硬芯：

        ## 角色设定表（锁一致性，每格 prompt 都带）
        - **角色名 / EnglishName（概念）**：精确外貌。性格=...
        - 关系：

        ## 角色指纹（防止逐格漂移）
        - 角色名：按原作和设定锁定肤色、年龄、体型、服装、标志物和比例
        - English lock: reference image, do not redesign the characters, clothing color is not skin color

        ## N 格分镜脚本（动态格数）
        1. **钩子** | 画面。台词。旁白必须先交代主角是谁和处境，再给主题。
        2. **铺设** | 画面。台词。旁白必须先字面、后主题。

        ## 标题候选（≤20 字）
        1.
        2.
        3.

        ## 角色定妆 Prompt
        ```text
        风格 spec + 角色全身设定 + 角色指纹 + neutral background + no speech bubbles
        ```

        ## 逐格图像执行说明
        ### 第 1 格
        ```text
        Do not generate this panel unless the approved 00-character-reference image is attached as an input/reference image.
        If a user-approved reference already exists, use that exact image; do not regenerate or improve the character design.
        reference image + 角色指纹 + do not redesign the characters + 风格 spec + Scene: ...
        Pose safety: adult ordinary proportions, natural readable limbs and hands, no warped anatomy, no extreme foreshortening, no mascot proportions.
        Text handling: no readable text, letters, numbers, prices, equations, or pseudo-text.
        Do not draw empty white rectangles, labels, tags, cards, signboards, UI screens, price stickers, text placeholders, or reserved text areas. Do not draw speech bubbles, caption boxes, bottom narration frames, or end-hook panels. Dialogue and narration are added later in the final layout.
        ```

叠字文本（后期添加，不放进图片 prompt）：
- 台词：
- 旁白：
        - 自检：是否先交代谁/发生什么，再讲主题；是否把文学/哲学/专业概念翻成大白话；是否有准确、克制的读者生活桥；是否有足够的画面事实、心理或因果推进、读者能带走的解释；最后一格是否先收束本话主题、再留不剧透悬念、并保留撩评论；如果是移动端轮播卡片，是否 ≤3 句并约砍 40%。
"""
    ).strip()
    return _strip_template_indent(prompt) + "\n"


def _book_label(package: AdaptationPackage) -> str:
    if package.author:
        return f"《{package.book_title}》（{package.author}）"
    return f"《{package.book_title}》"


def _join_items(items: tuple[str, ...]) -> str:
    return " + ".join(items)


def _render_panel_script(panel: Panel) -> str:
    parts = [f"{panel.index}. **{panel.beat}** | {panel.visual}"]
    if panel.dialogue:
        parts.append(" ".join(panel.dialogue))
    if panel.narration:
        parts.append(f"旁白：{panel.narration}")
    if panel.comment_hook:
        parts.append(f"撩评论：{panel.comment_hook}")
    return " ".join(parts)


def _character_prompt_lines(characters: tuple[Character, ...]) -> str:
    return "\n".join(f"- {character.prompt_fragment}" for character in characters)


def _indent_multiline(text: str, prefix: str) -> str:
    return "\n".join(prefix + line if line else prefix.rstrip() for line in text.splitlines())


def _strip_template_indent(text: str) -> str:
    return "\n".join(line[8:] if line.startswith("        ") else line for line in text.splitlines())


def _render_panel_prompt(
    panel: Panel,
    characters: tuple[Character, ...],
    style_prompt: str,
) -> list[str]:
    text = [
        "",
        f"### 第 {panel.index} 格 · {panel.beat}",
        "",
        "```text",
        "Do not generate this panel unless the approved 00-character-reference image is attached as an input/reference image.",
        "If a user-approved reference already exists, use that exact image; do not regenerate or improve the character design.",
        "Use the same reference image for character consistency.",
        "Character lock: do not redesign the characters; do not change clothing, skin tone, body proportions, face, glasses, or color ownership.",
        "Pose safety: adult ordinary proportions, natural readable limbs and hands, no warped anatomy, no extreme foreshortening, no mascot proportions.",
        "Colors belong to clothing, not skin.",
        style_prompt,
        "",
        "Characters:",
        _character_prompt_lines(characters),
        "",
        f"Scene: {panel.visual}",
        "Text handling: no readable text, letters, numbers, prices, equations, or pseudo-text in the generated image.",
        "Do not draw empty white rectangles, labels, tags, cards, signboards, UI screens, price stickers, text placeholders, or reserved text areas.",
        "Use objects, gestures, icons, anchors, carts, shelves, stamps, and character acting to express the idea instead of any text container.",
        "Do not draw speech bubbles. Do not draw caption boxes, bottom narration frames, large white text areas, or end-hook panels.",
        "Narration is added later in the final layout, outside the generated panel art; dialogue and hooks are also added there.",
    ]
    text.extend(["```"])

    overlay_lines = _overlay_text_lines(panel)
    if overlay_lines:
        text.extend(["", "叠字文本（后期添加，不放进图片 prompt）：", *overlay_lines])
    return text


def _overlay_text_lines(panel: Panel) -> list[str]:
    lines: list[str] = []
    for dialogue in panel.dialogue:
        lines.append(f"- 台词：{dialogue}")
    if panel.narration:
        lines.append(f"- 旁白：{panel.narration}")
    if panel.comment_hook:
        lines.append(f"- 撩评论：{panel.comment_hook}")
    return lines
