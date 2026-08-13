"""配置文件"""
import os
from dotenv import load_dotenv

load_dotenv()

# 大模型配置（主模型 + 备用模型）
LLM_CONFIG = {
    "api_key": os.getenv("OPENAI_API_KEY", ""),
    "base_url": os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
    "model_name": os.getenv("OPENAI_MODEL_NAME", "gpt-4o"),
}

# 备用模型列表（主模型挂了自动切换）
FALLBACK_MODELS = [
    {
        "api_key": os.getenv("FALLBACK_API_KEY", ""),
        "base_url": os.getenv("FALLBACK_BASE_URL", ""),
        "model_name": os.getenv("FALLBACK_MODEL_NAME", "gpt-3.5-turbo"),
    },
    {
        "api_key": os.getenv("FALLBACK2_API_KEY", ""),
        "base_url": os.getenv("FALLBACK2_BASE_URL", ""),
        "model_name": os.getenv("FALLBACK2_MODEL_NAME", "gpt-3.5-turbo"),
    },
]

# 系统提示词
SYSTEM_PROMPT = """你是智能客服助手，负责解答用户问题。
请做到：
1. 礼貌、简洁、准确
2. 如果不确定，诚实告知并建议转人工
3. 不要编造信息"""
