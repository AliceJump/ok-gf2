import hashlib
import json
import time

import requests


class CommunityMixin:
    BASE_API = "https://gf2-bbs-api.exiliumgf.com"
    PROXIES = {"http": "", "https": ""}
    COMMON_HEADERS = {
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0",
    }

    # ================== 通用请求 ==================
    def request_json(
        self,
        method: str,
        url: str,
        headers: dict | None = None,
        data: dict | None = None,
    ) -> dict | None:
        try:
            resp = requests.request(
                method=method,
                url=url,
                headers=headers,
                data=json.dumps(data) if data is not None else None,
                timeout=15,
                proxies=self.PROXIES,
            )
            return resp.json()
        except Exception as e:
            self.log_info("请求失败")
            self.log_info(f"请求方式: {method}")
            self.log_info(f"请求地址: {url}")
            self.log_info(f"错误信息: {e}")
            return None

    # ================== 登录 ==================
    @staticmethod
    def md5_hex(text: str) -> str:
        return hashlib.md5(text.encode("utf-8")).hexdigest()

    def login(self, account: str, password: str, source: str = "phone") -> str | None:
        self.log_info("开始登录")

        url = f"{self.BASE_API}/login/account"
        payload = {
            "account_name": account,
            "passwd": password,
            "source": source,
        }

        headers = {
            **self.COMMON_HEADERS,
            "Content-Type": "application/json",
        }

        data = self.request_json("POST", url, headers, payload)
        if not data:
            self.log_info("登录失败：接口无返回")
            return None

        if data.get("Code") == 0:
            token = data.get("data", {}).get("account", {}).get("token")
            if token:
                self.log_info("登录成功，token 已获取")
                return token

        self.log_info("登录失败")
        self.log_info(f"返回信息: {data.get('Message')}")
        return None

    # ================== 社区任务 ==================
    def sign_in(self, auth_token: str) -> bool:
        self.log_info("尝试每日签到")

        url = f"{self.BASE_API}/community/task/sign_in"
        headers = {**self.COMMON_HEADERS, "Authorization": auth_token}

        data = self.request_json("POST", url, headers)

        if data and data.get("Code") == 0:
            self.log_info("签到成功")
            return True

        self.log_info("签到失败或已签到")
        if data:
            self.log_info(f"返回信息: {data}")
        return False

    def get_top_topic_ids(self, count: int) -> list[int]:
        self.log_info(f"获取热门帖子（数量: {count}）")

        url = (
            f"{self.BASE_API}/community/topic/list"
            "?sort_type=1&category_id=1&query_type=1"
            "&last_tid=0&pub_time=0&reply_time=0&hot_value=0"
        )

        data = self.request_json("GET", url, self.COMMON_HEADERS)
        topic_list = data.get("data", {}).get("list", []) if data else []

        ids = [item.get("topic_id") for item in topic_list[:count]]
        self.log_info(f"获取到帖子 ID: {ids}")
        return ids

    def view_topic(self, auth_token: str, topic_id: int):
        url = f"{self.BASE_API}/community/topic/{topic_id}"
        headers = {**self.COMMON_HEADERS, "Authorization": auth_token}
        self.request_json("GET", url, headers)
        self.log_info(f"已浏览帖子: {topic_id}")

    def like_topic(self, auth_token: str, topic_id: int) -> bool:
        url = f"{self.BASE_API}/community/topic/like/{topic_id}"
        headers = {**self.COMMON_HEADERS, "Authorization": auth_token}
        data = self.request_json("GET", url, headers)
        return bool(data and data.get("Code") == 0)

    def ensure_like_once(self, auth_token: str, topic_id: int):
        self.log_info(f"点赞帖子: {topic_id}")
        self.like_topic(auth_token, topic_id)
        time.sleep(1.1)
        self.like_topic(auth_token, topic_id)

    def share_topic(self, auth_token: str, topic_id: int) -> bool:
        self.log_info(f"尝试分享帖子: {topic_id}")

        url = f"{self.BASE_API}/community/topic/share/{topic_id}"
        headers = {**self.COMMON_HEADERS, "Authorization": auth_token}

        data = self.request_json("GET", url, headers)
        if data and data.get("Code") == 0:
            self.log_info(f"分享成功: {topic_id}")
            return True

        self.log_info(f"分享失败: {topic_id}")
        return False

    # ================== 兑换 ==================
    def get_exchange_list(self, auth_token: str) -> list[dict]:
        self.log_info("获取兑换列表")

        url = f"{self.BASE_API}/community/item/exchange_list"
        headers = {**self.COMMON_HEADERS, "Authorization": auth_token}

        data = self.request_json("GET", url, headers)
        items = data.get("data", {}).get("list", []) if data else []

        self.log_info(f"可兑换项目数量: {len(items)}")
        return items

    def get_user_score(self, auth_token: str) -> int | None:
        self.log_info("查询当前积分")

        url = f"{self.BASE_API}/community/member/info"
        headers = {**self.COMMON_HEADERS, "Authorization": auth_token}

        try:
            data = self.request_json("POST", url, headers=headers, data={})

        except Exception as e:
            self.log_info(f"请求或解析 JSON 出错:{e}")
            return None

        if data.get("Code") != 0:
            self.log_info(f"获取积分失败:{data}")
            return None
        score = data.get("data", {}).get("user", {}).get("score")
        self.log_info(f"积分剩余:{score}")
        return score

    def exchange_item(self, auth_token: str, exchange_id: int) -> bool:
        url = f"{self.BASE_API}/community/item/exchange"
        headers = {
            **self.COMMON_HEADERS,
            "Authorization": auth_token,
            "Content-Type": "application/json",
        }

        resp = requests.post(
            url,
            headers=headers,
            json={"exchange_id": exchange_id},
            timeout=15,
            proxies=self.PROXIES,
        )
        data = resp.json()
        return data.get("Code") == 0

    def auto_exchange(self, auth_token: str):
        self.log_info("开始自动兑换")

        score = self.get_user_score(auth_token)
        if score is None:
            return

        items = self.get_exchange_list(auth_token)
        for item in items:
            exchange_id = item["exchange_id"]
            max_count = item["max_exchange_count"]
            used_count = item["exchange_count"]
            remain = max_count - used_count
            cost = item["use_score"]

            self.log_info(f"兑换项目 exchange_id={exchange_id}")
            self.log_info(f"已兑换 {used_count}/{max_count} 次，单次消耗 {cost}")

            # 情况 1：次数已用完
            if remain <= 0:
                self.log_info("已达到兑换上限，跳过该项目")
                continue

            max_by_score = score // cost
            times = min(remain, max_by_score)

            # 情况 2：积分不足
            if max_by_score <= 0:
                self.log_info(f"当前积分不足（需要 {cost}，剩余 {score}），跳过")
                continue

            # 情况 3：可兑换
            self.log_info(f"剩余可兑换次数 {remain}")
            self.log_info(f"本次计划兑换 {times} 次")

            for i in range(times):
                if not self.exchange_item(auth_token, exchange_id):
                    self.log_info("本次兑换失败，中断该项目")
                    break

                score -= cost
                self.log_info(f"兑换成功 {i + 1}/{times}，剩余积分 {score}")

    # ================== 主流程 ==================
    def daily_tasks(self, auth_token: str):
        self.log_info("开始执行每日任务")

        self.sign_in(auth_token)

        topics = self.get_top_topic_ids(5)
        if not topics:
            self.log_info("未获取到可用帖子，跳过浏览/点赞/分享")
            return

        for tid in topics[:3]:
            self.view_topic(auth_token, tid)
            time.sleep(0.6)

        for tid in topics[:3]:
            self.ensure_like_once(auth_token, tid)
            time.sleep(1.2)

        self.share_topic(auth_token, topics[0])
        self.log_info("每日任务完成")

    def run_community_flow(self, user: str, pwd: str) -> bool:
        token = None

        for login_type in ("mail", "phone"):
            token = self.login(user, pwd, login_type)
            if token:
                break
            time.sleep(1)

        if token:
            self.daily_tasks(token)
            self.auto_exchange(token)
            return True

        self.log_info("未登录")
        return False

    def main(self, user, pwd):
        return self.run_community_flow(user, pwd)
