# shared/integrations/wecom/client.py
"""
WecomClient - 企业微信 API 客户端

职责：
1. access_token 管理（自动刷新）
2. 消息发送（文本、卡片）
3. 卡片更新
"""
import asyncio
import time
from typing import Optional

import httpx

from shared.utils.logger import get_logger

logger = get_logger("wecom.client")


class WecomClient:
    """
    企业微信 API 客户端

    使用方式:
        client = WecomClient(corp_id, secret, agent_id)
        await client.send_text_message(user_id, "Hello")
        await client.send_template_card(user_id, card)
    """

    TOKEN_EXPIRE_BUFFER = 300

    def __init__(
        self,
        corp_id: str,
        secret: str,
        agent_id: int,
        base_url: str = "https://qyapi.weixin.qq.com/cgi-bin",
    ):
        self.corp_id = corp_id
        self.secret = secret
        self.agent_id = agent_id
        self.base_url = base_url

        self._token: Optional[str] = None
        self._token_expires_at: float = 0
        self._lock = asyncio.Lock()

    def _is_token_valid(self) -> bool:
        """检查 token 是否有效"""
        if not self._token:
            return False
        return time.time() < (self._token_expires_at - self.TOKEN_EXPIRE_BUFFER)

    async def _refresh_token(self) -> str:
        """从企微 API 获取新 token"""
        url = f"{self.base_url}/gettoken"
        params = {
            "corpid": self.corp_id,
            "corpsecret": self.secret,
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, timeout=10.0)
            response.raise_for_status()
            data = response.json()

        if data.get("errcode") != 0:
            logger.error("wecom_token_error", code=data.get("errcode"), msg=data.get("errmsg"))
            raise ValueError(f"Failed to get token: {data.get('errmsg')}")

        self._token = data["access_token"]
        self._token_expires_at = time.time() + data["expires_in"]

        logger.info("wecom_token_refreshed", expires_in=data["expires_in"])
        return self._token

    async def get_access_token(self) -> str:
        """获取 access_token，自动刷新"""
        async with self._lock:
            if self._is_token_valid():
                return self._token
            return await self._refresh_token()

    async def send_text_message(self, user_id: str, content: str) -> str:
        """发送文本消息"""
        token = await self.get_access_token()
        url = f"{self.base_url}/message/send"
        params = {"access_token": token}
        payload = {
            "touser": user_id,
            "msgtype": "text",
            "agentid": self.agent_id,
            "text": {"content": content},
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(url, params=params, json=payload, timeout=10.0)
            response.raise_for_status()
            data = response.json()

        if data.get("errcode") != 0:
            logger.error("wecom_send_text_error", code=data.get("errcode"), msg=data.get("errmsg"))
            raise ValueError(f"Failed to send message: {data.get('errmsg')}")

        logger.info("wecom_text_sent", user_id=user_id, msgid=data.get("msgid"))
        return data.get("msgid", "")

    async def send_template_card(self, user_id: str, card: dict) -> str:
        """发送模板卡片消息"""
        token = await self.get_access_token()
        url = f"{self.base_url}/message/send"
        params = {"access_token": token}
        payload = {
            "touser": user_id,
            "msgtype": "template_card",
            "agentid": self.agent_id,
            "template_card": card,
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(url, params=params, json=payload, timeout=10.0)
            response.raise_for_status()
            data = response.json()

        if data.get("errcode") != 0:
            logger.error("wecom_send_card_error", code=data.get("errcode"), msg=data.get("errmsg"))
            raise ValueError(f"Failed to send card: {data.get('errmsg')}")

        logger.info("wecom_card_sent", user_id=user_id, msgid=data.get("msgid"))
        return data.get("msgid", "")

    async def update_template_card(self, response_code: str, card: dict) -> bool:
        """更新模板卡片"""
        token = await self.get_access_token()
        url = f"{self.base_url}/message/update_template_card"
        params = {"access_token": token}
        payload = {
            "userids": [],
            "agentid": self.agent_id,
            "response_code": response_code,
            "template_card": card,
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(url, params=params, json=payload, timeout=10.0)
            response.raise_for_status()
            data = response.json()

        if data.get("errcode") != 0:
            logger.error("wecom_update_card_error", code=data.get("errcode"), msg=data.get("errmsg"))
            return False

        logger.info("wecom_card_updated", response_code=response_code[:20])
        return True

    async def get_user_info(self, user_id: str) -> dict:
        """
        获取用户信息

        通过企微通讯录 API 获取用户详情。

        Args:
            user_id: 企微成员 UserID

        Returns:
            用户信息字典，包含 name, email 等字段
        """
        token = await self.get_access_token()
        url = f"{self.base_url}/user/get"
        params = {
            "access_token": token,
            "userid": user_id,
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=params, timeout=10.0)
                response.raise_for_status()
                data = response.json()

            if data.get("errcode") != 0:
                logger.warning(
                    "wecom_get_user_error",
                    code=data.get("errcode"),
                    msg=data.get("errmsg"),
                    user_id=user_id,
                )
                return {"userid": user_id, "name": "Unknown"}

            return {
                "userid": data.get("userid", user_id),
                "name": data.get("name", "Unknown"),
                "email": data.get("email", ""),
                "mobile": data.get("mobile", ""),
                "avatar": data.get("avatar", ""),
            }
        except Exception as e:
            logger.warning("wecom_get_user_error", error=str(e), user_id=user_id)
            return {"userid": user_id, "name": "Unknown"}


# 全局客户端实例
_wecom_client: Optional[WecomClient] = None


def get_wecom_client() -> WecomClient:
    """获取企微客户端单例"""
    global _wecom_client
    if _wecom_client is None:
        from .config import get_wecom_config
        config = get_wecom_config()
        _wecom_client = WecomClient(
            corp_id=config.corp_id,
            secret=config.secret,
            agent_id=config.agent_id,
            base_url=config.api_base_url,
        )
    return _wecom_client


wecom_client = get_wecom_client
