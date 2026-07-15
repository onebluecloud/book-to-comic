from .models import AdaptationPackage, Character, CoreIdea, Panel, Suitability


def thinking_fast_and_slow_ep1() -> AdaptationPackage:
    return AdaptationPackage(
        book_title="思考,快与慢",
        author="丹尼尔·卡尼曼",
        episode_title="《思考,快与慢》EP1",
        suitability=Suitability(
            is_applicable=True,
            category="观点 / 认知型",
            reason="核心价值是记住几个观点和认知模型，而不是查询操作步骤，适合改编成多格漫画。",
        ),
        covered_points=(
            "系统1 vs 系统2",
            "锚定效应",
        ),
        core_ideas=(
            CoreIdea(
                title="系统1 vs 系统2",
                kernel="快脑负责秒判和日常直觉，慢脑负责深想和校验，但经常偷懒。",
                dramatization="概念拟人化：把两个系统变成同一座决策驾驶台上的快脑和慢脑。",
            ),
            CoreIdea(
                title="锚定效应",
                kernel="先出现的数字会成为心理锚，悄悄影响你后面的判断。",
                dramatization="案例情景剧：用购物划线价展示快脑被原价带跑、慢脑偷懒盖章。",
            ),
        ),
        methods=(
            "概念拟人化",
            "案例情景剧",
        ),
        light_shell="购物 / 剁手场景",
        hard_core="系统1/2 + 锚定效应",
        characters=(
            Character(
                name="快脑 / Fast",
                concept="系统1",
                visual="浅肤色脸和手，成人普通比例，椭圆脸，小眼睛，橙色刺发，橙色长袖上衣，深橙色裤子，黑色小鞋；表情急切自信，身体前倾像在抢话，胸口一道黄色小闪电徽章。",
                personality="冲动、自信、爱抄近路，错了也理直气壮。",
                prompt_fragment=(
                    "Fast (adult ordinary proportions, light skin face and hands, oval face, "
                    "small simple eyes, spiky orange hair, orange long-sleeve shirt, "
                    "dark orange trousers, black small shoes, tiny yellow lightning badge on chest, "
                    "cheerful eager smile, leaning forward excited)"
                ),
            ),
            Character(
                name="慢脑 / Slow",
                concept="系统2",
                visual="淡肤色脸和手，成人普通比例，椭圆脸，小眼睛，蓝色连帽开衫，白衬衫，深色裤子，圆框眼镜，黑眼圈，慵懒后靠，表情淡定疲惫。",
                personality="聪明但懒，能不动就不动，常懒得检查就给快脑盖章放行。",
                prompt_fragment=(
                    "Slow (adult ordinary proportions, pale face and hands, oval face, "
                    "small simple tired eyes, blue hooded cardigan, white shirt, dark trousers, "
                    "round glasses, eye-bags, thoughtful worried face, calm tired posture)"
                ),
            ),
        ),
        character_relationship="两人共用一座决策驾驶台，快脑抢答抢方向盘，慢脑负责校验但经常偷懒。",
        storyboard=(
            Panel(
                index=1,
                beat="钩子",
                visual="温暖的决策驾驶台工作室，前方是简洁无字的仪表盘和控制台。快脑坐前排抢方向盘，慢脑瘫在后排懒人椅上。",
                dialogue=(),
                narration="你以为做主的是「你」？其实决策驾驶台上常驻这俩 —— 平时是左边那个在开车。",
            ),
            Panel(
                index=2,
                beat="快脑登场",
                visual="快脑抢答，旁边飞出算盘珠、红灯图标、笑脸图标三个直觉符号。",
                dialogue=("快脑：2+2=4！红灯停！这人在笑=开心！",),
                narration="快脑（系统1）：秒出答案，管你 95% 的日常。快，但爱抄近路。",
            ),
            Panel(
                index=3,
                beat="慢脑登场",
                visual="慢脑葛优瘫，一团复杂线团和几个小齿轮滚到他面前。",
                dialogue=("慢脑：啊？……让我缓缓……好累。",),
                narration="慢脑（系统2）：能算对、会深想，但是个懒鬼。",
            ),
            Panel(
                index=4,
                beat="关键设定",
                visual="快脑递出一道闪电形想法，慢脑闭眼把印章盖在棕色文件夹上。",
                dialogue=(),
                narration="快脑抢答，慢脑懒得查，随手盖章放行。于是 ——",
            ),
            Panel(
                index=5,
                beat="锚定·上",
                visual="商店橱窗里摆着一个商品，商品旁边压着一只巨大的金属锚，快脑眼睛发光跳起来。",
                dialogue=("快脑：才 299？！便宜 700！买它！",),
                narration="",
            ),
            Panel(
                index=6,
                beat="锚定·下",
                visual="慢脑瘫着盖章，旁边购物车已经自己滑向收银台，快脑兴奋地推着车。",
                dialogue=("慢脑：快脑说划算……那就划算吧。",),
                narration="没人问：它本身到底值多少？",
            ),
            Panel(
                index=7,
                beat="点破",
                visual="商家躲在幕布后偷笑，悄悄把一只巨大的金属锚拴到购物车上。",
                dialogue=(),
                narration=(
                    "那 ¥999 是商家丢给你快脑的「锚」。你以为在算计，"
                    "其实被一个数字带跑、慢脑偷懒放行 —— 这就是「锚定效应」。"
                ),
            ),
            Panel(
                index=8,
                beat="收口 + 撩评论",
                visual="闹钟吵醒慢脑，慢脑坐起，一手拦住购物车，一手指向商品本身。",
                dialogue=("慢脑：抛开原价 —— 它本身值多少？",),
                narration="下次看到划线价，叫醒你的慢脑，问这一句就够了。",
                comment_hook="你最近被哪个「原价」套路过？",
            ),
        ),
        title_candidates=(
            "买东西总剁手？是你脑子里的“快脑”在抢答",
            "我把《思考,快与慢》画成漫画，这本天书终于秒懂",
            "你以为在思考，其实两个系统在抢方向盘",
        ),
        style_id="editorial",
    )
