"""结构化故障排查流程定义"""


# ── 排查流程库 ─────────────────────────────────────────────

TROUBLESHOOT_FLOWS = {
    "video_fail": {
        "name": "视频生成失败",
        "triggers": ["生成失败", "视频失败", "视频报错", "无法生成视频", "生成不了视频",
                     "视频生成不了", "生成错误", "failed", "视频生成失败", "生成不了"],
        "kb_categories": ["video_generation", "copyright", "content_policy", "prompt", "usage"],
        "max_steps": 3,
        "steps": [
            {
                "id": "step0",
                "question": "请问有报错提示吗？可以把错误信息或截图发给我，我帮你看看是什么问题。",
                "branches": [
                    {"keywords": ["版权", "copyright", "限制"], "next": "solve_copyright"},
                    {"keywords": ["敏感", "违规", "色情", "暴力", "政治"], "next": "solve_sensitive"},
                    {"keywords": ["字数", "超长", "限制", "1024", "过长"], "next": "solve_prompt_length"},
                    {"keywords": ["超时", "卡住", "没反应", "等待", "太慢"], "next": "solve_timeout"},
                    {"keywords": ["积分", "余额", "不够", "不足"], "next": "solve_credits"},
                ],
                "default_next": "step1",
            },
            {
                "id": "step1",
                "question": "能描述一下具体的操作步骤和现象吗？比如用的什么模型、提示词大概多长、等了多久？",
                "branches": [
                    {"keywords": ["v3", "慢"], "next": "solve_v3_slow"},
                    {"keywords": ["提示词", "不像", "不对"], "next": "solve_quality"},
                    {"keywords": ["参考图", "角色", "人脸"], "next": "solve_reference"},
                ],
                "default_next": "step2",
            },
            {
                "id": "step2",
                "question": "明白。请把 TaskID 发给我，我帮你提交工单让客服排查一下。你可以点击「转人工客服」按钮提交。",
                "branches": [],
                "default_next": "done",
            },
        ],
        "solutions": {
            "solve_copyright": (
                "这是版权限制，是火山引擎的统一拦截机制。建议：\n"
                "1. 调整提示词，避免明确提及版权角色名或品牌名\n"
                "2. 使用大头照+正面全身照两张参考图来锚定角色\n"
                "3. 尝试使用 Neo Image 2 official 模型，审核相对宽松\n"
                "4. 点击顶部工具栏的「校验」按钮可提前检测内容\n"
                "5. 如确认内容不侵权，可点击「转人工客服」提交工单并附上 TaskID 申请豁免"
            ),
            "solve_sensitive": (
                "这是敏感内容拦截，与版权限制不同，是火山引擎对提示词中暴力、色情、政治等敏感信息的检测。\n"
                "建议：\n"
                "1. 检查提示词是否有不当描述\n"
                "2. 避免明确提及敏感话题\n"
                "3. 如确认内容合规仍被拒（可能是误伤），可点击「转人工客服」提交工单并附上 TaskID 和画布浏览器地址，客服会向火山引擎申请豁免"
            ),
            "solve_prompt_length": (
                "不同模型有提示词长度限制（如v8模型限制1024字符）。\n"
                "建议：\n"
                "1. 精简描述，保留核心要素\n"
                "2. 分段生成后拼接\n"
                "3. 优先描述主体和风格，省略细节"
            ),
            "solve_timeout": (
                "正常等待时间参考：图片生成1-5分钟，视频生成5-30分钟。\n"
                "超分辨率目前使用量较大，需要排队，可能需要更长时间。\n"
                "v3模型速度较慢属正常现象。\n"
                "如超过30分钟仍未完成，可能是队列拥堵或任务异常，可点击「转人工客服」提交工单并附上 TaskID 排查。"
            ),
            "solve_credits": (
                "积分不足无法生成。可在账户中心查看积分余额和明细。\n"
                "充值方式：支付宝/微信支付/银行卡（1积分=¥0.01），礼品卡享8折优惠。\n"
                "会员也可获得每月免费生成额度和消费折扣。"
            ),
            "solve_v3_slow": (
                "v3模型生成速度较慢属于正常现象。如果赶时间，可以切换至v8模型，速度更快且提示词理解能力更强（上限1024字符）。"
            ),
            "solve_quality": (
                "如果生成的视频没有按照提示词来，建议：\n"
                "1. 检查提示词是否足够清晰明确\n"
                "2. 避免同时描述过多元素，模型可能注意力分散\n"
                "3. 尝试更换模型\n"
                "4. 使用参考图锚定角色和场景\n"
                "如反复尝试仍不理想，可点击「转人工客服」反馈，我们会向火山引擎提交提示词优化方案。"
            ),
            "solve_reference": (
                "参考图使用建议：\n"
                "1. 使用1-2张参考图即可，过多会使模型注意力不集中\n"
                "2. 大头照尽量减少肩颈入镜，让模型更好地获取面部信息\n"
                "3. 搭配正面全身照锚定角色整体形象\n"
                "过多参考元素会导致人脸漂移进而触发版权检测。"
            ),
        },
    },

    "image_fail": {
        "name": "图片生成失败",
        "triggers": ["图片失败", "生成不了图", "图片生成失败", "图生不出来", "图片报错",
                     "图片生成不出来", "生成不出图片", "图片无法生成"],
        "kb_categories": ["image_generation", "copyright", "content_policy", "prompt"],
        "max_steps": 3,
        "steps": [
            {
                "id": "step0",
                "question": "请问有报错提示吗？可以把错误信息或截图发给我。",
                "branches": [
                    {"keywords": ["版权", "限制", "copyright"], "next": "solve_copyright"},
                    {"keywords": ["敏感", "违规"], "next": "solve_sensitive"},
                    {"keywords": ["字数", "超长"], "next": "solve_prompt_length"},
                ],
                "default_next": "step1",
            },
            {
                "id": "step1",
                "question": "用的什么模型？提示词大概多长？可以描述一下你想生成什么内容。",
                "branches": [
                    {"keywords": ["积分", "余额"], "next": "solve_credits"},
                ],
                "default_next": "step2",
            },
            {
                "id": "step2",
                "question": "了解。请提供 TaskID，点击「转人工客服」提交工单，客服会帮你排查。",
                "branches": [],
                "default_next": "done",
            },
        ],
        "solutions": {
            "solve_copyright": (
                "图片生成也有版权检测。建议：\n"
                "1. 避免提示词中出现知名IP形象、品牌logo\n"
                "2. 尝试使用 Neo Image 2 official 模型，审核相对宽松\n"
                "3. 点击顶部「校验」按钮提前检测\n"
                "4. 如确认不侵权，点击「转人工客服」提交 TaskID 申请豁免"
            ),
            "solve_sensitive": (
                "敏感内容拦截是火山引擎对提示词中暴力、色情、政治等敏感信息的检测。\n"
                "建议检查提示词，如确认合规可点击「转人工客服」申请豁免。"
            ),
            "solve_prompt_length": (
                "不同模型有提示词长度限制。建议精简描述，保留核心要素，优先描述主体和风格。"
            ),
            "solve_credits": (
                "积分不足无法生成。可在账户中心查看余额。充值汇率：1积分=¥0.01，礼品卡8折。"
            ),
        },
    },

    "timeout": {
        "name": "任务等待太久",
        "triggers": ["太慢了", "等了很久", "卡住了", "等待时间", "怎么还没好", "生成好慢",
                     "等了好久", "一直等待", "没反应", "卡住不动"],
        "kb_categories": ["usage", "video_generation"],
        "max_steps": 2,
        "steps": [
            {
                "id": "step0",
                "question": "请问是什么任务？等了大概多久了？（图片/视频/超分/其他）",
                "branches": [
                    {"keywords": ["超分", "超清", "放大"], "next": "solve_upscale_wait"},
                    {"keywords": ["视频"], "next": "solve_video_wait"},
                    {"keywords": ["图片"], "next": "solve_image_wait"},
                ],
                "default_next": "step1",
            },
            {
                "id": "step1",
                "question": "请提供 TaskID，点击「转人工客服」提交工单，客服帮你查看任务状态。",
                "branches": [],
                "default_next": "done",
            },
        ],
        "solutions": {
            "solve_upscale_wait": (
                "超分辨率目前使用量较大，需要排队，等待时间取决于视频长度和分辨率。\n"
                "高峰期可能需要更长时间。如超过30分钟，可点击「转人工客服」提交工单并附上 TaskID 核实，或取消后重试。"
            ),
            "solve_video_wait": (
                "视频生成正常等待时间5-30分钟。v3模型会慢一些，属正常现象。\n"
                "如超过30分钟仍未完成，可能是队列拥堵或任务异常，可点击「转人工客服」提交工单并附上 TaskID 排查。"
            ),
            "solve_image_wait": (
                "图片生成正常等待时间1-5分钟。如超过5分钟，可能是队列拥堵。\n"
                "可点击「转人工客服」提交工单并附上 TaskID 排查。"
            ),
        },
    },

    "quality": {
        "name": "生成质量不好",
        "triggers": ["不像", "不对", "质量差", "效果不好", "和提示词不一样", "生成错了",
                     "效果不对", "生成效果不好", "不满意", "生成的不对"],
        "kb_categories": ["video_generation", "image_generation", "prompt"],
        "max_steps": 3,
        "steps": [
            {
                "id": "step0",
                "question": "具体是哪里不满意？是角色不像、场景不对、还是整体质量有问题？",
                "branches": [
                    {"keywords": ["角色", "人脸", "不像", "漂移"], "next": "solve_face_drift"},
                    {"keywords": ["场景", "背景", "环境"], "next": "solve_scene"},
                    {"keywords": ["质量", "模糊", "分辨率"], "next": "solve_resolution"},
                ],
                "default_next": "step1",
            },
            {
                "id": "step1",
                "question": "用的什么模型和提示词？有参考图吗？",
                "branches": [
                    {"keywords": ["参考图", "有"], "next": "solve_reference_quality"},
                    {"keywords": ["没有", "无"], "next": "solve_no_reference"},
                ],
                "default_next": "step2",
            },
            {
                "id": "step2",
                "question": "建议尝试调整提示词或更换模型。如反复尝试仍不理想，可点击「转人工客服」反馈，我们会向火山引擎提交提示词优化方案。",
                "branches": [],
                "default_next": "done",
            },
        ],
        "solutions": {
            "solve_face_drift": (
                "人脸漂移通常是因为参考元素过多导致模型注意力不集中。\n"
                "建议：\n"
                "1. 使用大头照+正面全身照两张参考图来锚定角色\n"
                "2. 大头照尽量减少肩颈入镜\n"
                "3. 避免同时使用过多参考元素"
            ),
            "solve_scene": (
                "场景不准确可能是提示词描述不够具体。\n"
                "建议：\n"
                "1. 明确描述环境、光线、氛围\n"
                "2. 避免过多元素堆砌\n"
                "3. 可尝试更换模型"
            ),
            "solve_resolution": (
                "画质问题可以在生成时选择更高的分辨率选项。\n"
                "生成后也可以用超分功能提升画质。\n"
                "不同模型的画质表现有差异，可以尝试更换模型。"
            ),
            "solve_reference_quality": (
                "有参考图但效果不好，建议：\n"
                "1. 确保参考图清晰、正面\n"
                "2. 大头照减少肩颈入镜\n"
                "3. 参考图不要过多（1-2张最佳）\n"
                "4. 尝试更换模型"
            ),
            "solve_no_reference": (
                "没有参考图时，模型只能根据提示词生成，效果可能不稳定。\n"
                "建议添加1-2张参考图来锚定角色和场景，效果会更可控。"
            ),
        },
    },

    "account_issue": {
        "name": "账号/积分问题",
        "triggers": ["积分没了", "扣多了", "账号问题", "积分少了", "积分突然少了", "会员到期", "充值没到账"],
        "kb_categories": ["billing", "account"],
        "max_steps": 2,
        "steps": [
            {
                "id": "step0",
                "question": "请问具体是什么问题？是积分突然变少、充值没到账、还是会员相关的问题？",
                "branches": [
                    {"keywords": ["积分", "少了", "扣多"], "next": "solve_credits_deduct"},
                    {"keywords": ["充值", "没到账"], "next": "solve_recharge"},
                    {"keywords": ["会员", "到期", "续费"], "next": "solve_member"},
                ],
                "default_next": "step1",
            },
            {
                "id": "step1",
                "question": "了解。这类问题需要客服在后台核实，请点击「转人工客服」提交工单，客服会尽快帮你处理。",
                "branches": [],
                "default_next": "done",
            },
        ],
        "solutions": {
            "solve_credits_deduct": (
                "积分减少可能原因：\n"
                "1. 生成任务消耗（视频/图片生成都消耗积分）\n"
                "2. 积分有有效期，过期会清零\n"
                "3. 系统调整\n"
                "可在账户中心查看积分明细。如异常减少，请点击「转人工客服」联系核查。"
            ),
            "solve_recharge": (
                "充值后积分一般即时到账。如未到账，可能是系统延迟，一般24小时内到账。\n"
                "超过24小时请点击「转人工客服」联系处理。"
            ),
            "solve_member": (
                "会员周期按充值时间计算（30天月付/365天年付）。\n"
                "暂不支持在会员未过期时续费，需要等当前会员到期后再续费。\n"
                "月付续费不再赠送额外积分，年付续费仍赠送。\n"
                "如有其他会员问题，请点击「转人工客服」咨询。"
            ),
        },
    },

    "upscale_fail": {
        "name": "超分辨率失败",
        "triggers": ["超分失败", "超清失败", "放大失败", "分辨率提升失败",
                     "超分报错", "放大报错", "超分辨率失败", "upscal失败"],
        "kb_categories": ["upscale", "video_generation", "image_generation"],
        "max_steps": 2,
        "steps": [
            {
                "id": "step0",
                "question": "请问超分的是图片还是视频？有报错提示吗？可以把错误信息或截图发给我。",
                "branches": [
                    {"keywords": ["视频", "video"], "next": "solve_video_upscale"},
                    {"keywords": ["图片", "image", "照片"], "next": "solve_image_upscale"},
                    {"keywords": ["版权", "限制", "copyright"], "next": "solve_upscale_copyright"},
                ],
                "default_next": "step1",
            },
            {
                "id": "step1",
                "question": "了解。请提供 TaskID，点击「转人工客服」提交工单，客服会帮你排查超分失败的原因。",
                "branches": [],
                "default_next": "done",
            },
        ],
        "solutions": {
            "solve_video_upscale": (
                "视频超分辨率失败可能原因：\n"
                "1. 视频时长过长（建议不超过30秒）\n"
                "2. 分辨率过高（4K以上处理时间较长）\n"
                "3. 服务器队列拥堵\n"
                "4. 涉及版权内容被拦截\n"
                "建议：缩短视频时长或降低目标分辨率后重试。如反复失败，请点击「转人工客服」提交 TaskID 排查。"
            ),
            "solve_image_upscale": (
                "图片超分辨率失败可能原因：\n"
                "1. 图片尺寸过小（建议不低于512x512）\n"
                "2. 图片格式不支持（支持 JPG/PNG/WEBP）\n"
                "3. 图片涉及版权内容被拦截\n"
                "建议：检查图片格式和尺寸后重试。如确认合规仍失败，请点击「转人工客服」提交 TaskID 申请核查。"
            ),
            "solve_upscale_copyright": (
                "超分辨率也有版权检测。如果原图/视频涉及版权内容（知名IP、品牌logo等），会被火山引擎统一拦截。\n"
                "建议：\n"
                "1. 使用原创内容或已获得授权的内容\n"
                "2. 如确认不侵权，点击「转人工客服」提交 TaskID 申请豁免"
            ),
        },
    },

    "payment_fail": {
        "name": "支付失败",
        "triggers": ["支付失败", "充值失败", "付款失败", "扣款失败",
                     "支付报错", "充值报错", "付不了款", "无法支付"],
        "kb_categories": ["billing", "payment", "account"],
        "max_steps": 2,
        "steps": [
            {
                "id": "step0",
                "question": "请问用的什么支付方式？（支付宝/微信/银行卡/礼品卡）有报错提示吗？",
                "branches": [
                    {"keywords": ["支付宝", "alipay"], "next": "solve_alipay"},
                    {"keywords": ["微信", "wechat"], "next": "solve_wechat"},
                    {"keywords": ["银行卡", "信用卡", "card"], "next": "solve_card"},
                    {"keywords": ["礼品卡", "gift"], "next": "solve_gift_card"},
                ],
                "default_next": "step1",
            },
            {
                "id": "step1",
                "question": "了解。支付问题需要客服在后台核实，请点击「转人工客服」提交工单，客服会尽快帮你处理。",
                "branches": [],
                "default_next": "done",
            },
        ],
        "solutions": {
            "solve_alipay": (
                "支付宝支付失败可能原因：\n"
                "1. 账户余额不足\n"
                "2. 支付限额\n"
                "3. 网络问题\n"
                "4. 支付宝风控拦截\n"
                "建议：检查账户余额后重试，或换用微信支付。如反复失败，请点击「转人工客服」联系处理。"
            ),
            "solve_wechat": (
                "微信支付失败可能原因：\n"
                "1. 微信账户异常\n"
                "2. 支付限额\n"
                "3. 网络问题\n"
                "建议：检查微信账户状态后重试，或换用支付宝。如反复失败，请点击「转人工客服」联系处理。"
            ),
            "solve_card": (
                "银行卡/信用卡支付失败可能原因：\n"
                "1. 卡内余额不足\n"
                "2. 银行风控拦截\n"
                "3. 卡片过期\n"
                "4. 不支持该卡类型\n"
                "建议：联系银行确认卡片状态，或换用支付宝/微信支付。如确认卡片正常仍失败，请点击「转人工客服」联系处理。"
            ),
            "solve_gift_card": (
                "礼品卡兑换失败可能原因：\n"
                "1. 卡密错误（注意区分大小写）\n"
                "2. 礼品卡已过期\n"
                "3. 礼品卡已被使用\n"
                "4. 礼品卡渠道不符（如平台限定卡）\n"
                "建议：核对卡密后重试。如确认卡密无误仍失败，请点击「转人工客服」提交卡密信息核查。"
            ),
        },
    },

    "skill_sync_fail": {
        "name": "技能同步失败",
        "triggers": ["技能同步失败", "技能同步不了", "技能更新失败",
                     "技能报错", "技能用不了", "技能加载失败"],
        "kb_categories": ["skill", "market"],
        "max_steps": 2,
        "steps": [
            {
                "id": "step0",
                "question": "请问是市场下载的技能还是自己上传的技能？有报错提示吗？",
                "branches": [
                    {"keywords": ["市场", "下载", "install"], "next": "solve_market_skill"},
                    {"keywords": ["上传", "自己", "custom"], "next": "solve_custom_skill"},
                ],
                "default_next": "step1",
            },
            {
                "id": "step1",
                "question": "了解。技能问题需要客服在后台核实，请点击「转人工客服」提交工单，客服会尽快帮你处理。",
                "branches": [],
                "default_next": "done",
            },
        ],
        "solutions": {
            "solve_market_skill": (
                "市场技能同步失败可能原因：\n"
                "1. 网络问题（技能文件较大）\n"
                "2. 技能版本与平台不兼容\n"
                "3. 技能已被作者下架\n"
                "4. 存储空间不足\n"
                "建议：检查网络后重试，或清除缓存后重新下载。如反复失败，请点击「转人工客服」提交技能名称和报错截图。"
            ),
            "solve_custom_skill": (
                "自己上传的技能同步失败可能原因：\n"
                "1. 技能文件格式错误\n"
                "2. 技能代码有语法错误\n"
                "3. 依赖库缺失\n"
                "4. 权限配置问题\n"
                "建议：检查技能文件格式和代码逻辑，参考官方技能开发文档。如确认代码无误仍失败，请点击「转人工客服」提交技能文件排查。"
            ),
        },
    },

    "canvas_crash": {
        "name": "画布崩溃",
        "triggers": ["画布崩溃", "画布卡死", "画布闪退", "项目崩溃",
                     "画布报错", "项目报错", "打不开画布", "画布加载失败"],
        "kb_categories": ["canvas", "project", "bug"],
        "max_steps": 3,
        "steps": [
            {
                "id": "step0",
                "question": "请问是打开画布时崩溃还是编辑过程中崩溃？有报错提示吗？",
                "branches": [
                    {"keywords": ["打开", "加载", "启动"], "next": "solve_canvas_load"},
                    {"keywords": ["编辑", "保存", "操作"], "next": "solve_canvas_edit"},
                ],
                "default_next": "step1",
            },
            {
                "id": "step1",
                "question": "请问用的是什么浏览器？可以尝试清理浏览器缓存后重试。",
                "branches": [
                    {"keywords": ["chrome", "谷歌"], "next": "solve_chrome"},
                    {"keywords": ["edge", "微软"], "next": "solve_edge"},
                ],
                "default_next": "step2",
            },
            {
                "id": "step2",
                "question": "了解。画布崩溃问题需要客服在后台核实，请点击「转人工客服」提交工单，客服会尽快帮你处理。",
                "branches": [],
                "default_next": "done",
            },
        ],
        "solutions": {
            "solve_canvas_load": (
                "打开画布时崩溃可能原因：\n"
                "1. 浏览器缓存问题\n"
                "2. 项目文件损坏\n"
                "3. 浏览器版本过旧\n"
                "建议：\n"
                "1. 清理浏览器缓存（Ctrl+Shift+Delete）\n"
                "2. 更新浏览器到最新版本\n"
                "3. 尝试用 Chrome 浏览器打开\n"
                "如仍崩溃，请点击「转人工客服」提交项目 ID 排查。"
            ),
            "solve_canvas_edit": (
                "编辑过程中崩溃可能原因：\n"
                "1. 项目元素过多（建议不超过100个）\n"
                "2. 内存不足\n"
                "3. 浏览器插件冲突\n"
                "建议：\n"
                "1. 关闭其他占用内存的程序\n"
                "2. 禁用浏览器插件后重试\n"
                "3. 定期保存项目（Ctrl+S）\n"
                "如反复崩溃，请点击「转人工客服」提交项目 ID 和浏览器信息。"
            ),
            "solve_chrome": (
                "Chrome 浏览器崩溃建议：\n"
                "1. 更新到最新版本（设置 → 关于 Chrome）\n"
                "2. 清理缓存（Ctrl+Shift+Delete → 选择全部时间）\n"
                "3. 禁用硬件加速（设置 → 系统 → 关闭硬件加速）\n"
                "4. 尝试无痕模式（Ctrl+Shift+N）\n"
                "如仍崩溃，请点击「转人工客服」提交 Chrome 版本号和报错截图。"
            ),
            "solve_edge": (
                "Edge 浏览器崩溃建议：\n"
                "1. 更新到最新版本（设置 → 关于 Microsoft Edge）\n"
                "2. 清理缓存（Ctrl+Shift+Delete）\n"
                "3. 尝试切换浏览器引擎（设置 → 默认浏览器 → 允许在 Internet Explorer 模式下重新加载）\n"
                "4. 尝试用 Chrome 浏览器打开\n"
                "如仍崩溃，请点击「转人工客服」提交 Edge 版本号和报错截图。"
            ),
        },
    },
}


def match_flow(user_input: str) -> str | None:
    """根据用户输入匹配排查流程"""
    user_lower = user_input.lower()
    best_match = None
    best_score = 0

    for flow_id, flow in TROUBLESHOOT_FLOWS.items():
        score = sum(1 for kw in flow["triggers"] if kw.lower() in user_lower)
        if score > best_score:
            best_score = score
            best_match = flow_id

    return best_match if best_score > 0 else None


def get_flow(flow_id: str) -> dict | None:
    """获取排查流程定义"""
    return TROUBLESHOOT_FLOWS.get(flow_id)


def get_step(flow: dict, step_id: str) -> dict | None:
    """获取流程中的某个步骤"""
    for step in flow.get("steps", []):
        if step["id"] == step_id:
            return step
    return None


def match_branch(step: dict, user_input: str) -> str:
    """根据用户输入匹配步骤中的分支"""
    user_lower = user_input.lower()
    for branch in step.get("branches", []):
        for kw in branch.get("keywords", []):
            if kw.lower() in user_lower:
                return branch["next"]
    return step.get("default_next", "done")


def get_solution(flow: dict, solution_id: str) -> str:
    """获取解决方案文本"""
    return flow.get("solutions", {}).get(solution_id, "")


def get_kb_context(flow: dict, faq_data: list) -> str:
    """从知识库中提取与当前排查流程相关的FAQ上下文"""
    categories = flow.get("kb_categories", [])
    context_parts = []

    for item in faq_data:
        # item 格式: (question, answer, category) 或 (question, answer, category, images)
        category = item[2] if len(item) > 2 else ""
        if category in categories:
            context_parts.append(f"Q: {item[0]}\nA: {item[1]}")

    return "\n\n".join(context_parts[:5])  # 最多取5条
