"""高德 Web 服务适配层：字段映射、infocode 映射、类型归一（BACKEND.md 15.4/15.9/15.10）。

这一层是唯一知道"高德长什么样"的地方。Server 只调这里的方法，拿到的已经是
项目自己的字段。换数据源只改这个文件。
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger("tpa.mcp.amap")

BASE_URL = "https://restapi.amap.com"

# 15.4 infocode -> 工具错误码
INFOCODE_TO_ERROR: dict[str, str] = {
    "10001": "UPSTREAM_AUTH_FAILED",
    "10005": "UPSTREAM_AUTH_FAILED",
    "10009": "UPSTREAM_AUTH_FAILED",
    "10003": "UPSTREAM_RATE_LIMITED",
    "10004": "UPSTREAM_RATE_LIMITED",
    "10044": "UPSTREAM_RATE_LIMITED",
    "20000": "INVALID_ARGUMENT",
    "20001": "INVALID_ARGUMENT",
    "20002": "INVALID_ARGUMENT",
    "20800": "INVALID_ARGUMENT",
    "20801": "INVALID_ARGUMENT",
    "20802": "NOT_FOUND",
    "30000": "TIMEOUT",
}


class AmapError(Exception):
    """内部异常，由 Server 转成信封。"""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


# ---------------------------------------------------------------------------
# 类型归一（15.9 三个坑）
# ---------------------------------------------------------------------------


def clean(value: Any) -> Any:
    """高德用空数组代替空值：`"tel": []`、`"cityname": []`。含字符串 `"[]"`。"""
    if isinstance(value, list):
        return None
    if isinstance(value, str) and value.strip() in ("[]", ""):
        return None
    return value


def to_int(value: Any, field: str = "?") -> int | None:
    """数字是字符串：`"distance": "4820"`。统一 int(float(x))。"""
    value = clean(value)
    if value is None:
        return None
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        logger.warning("字段 %s 无法转成整数: %r", field, value)
        return None


def to_cent(value: Any) -> int | None:
    """元 -> 分。"""
    value = clean(value)
    if value is None:
        return None
    try:
        return int(round(float(str(value).strip()) * 100))
    except (TypeError, ValueError):
        return None


def to_str(value: Any) -> str | None:
    value = clean(value)
    if value is None:
        return None
    return str(value)


def _normalize_location(value: Any) -> str | None:
    """坐标统一成 6 位小数的 "经度,纬度"。"""
    text = to_str(value)
    if not text or "," not in text:
        return text
    lng, _, lat = text.partition(",")
    try:
        return f"{float(lng):.6f},{float(lat):.6f}"
    except ValueError:
        return text


def validate_location(value: Any, field: str) -> str:
    text = _normalize_location(value)
    if not text or "," not in (text or ""):
        raise AmapError("INVALID_ARGUMENT", f"{field} 必须是 \"经度,纬度\" 形式")
    return text


# ---------------------------------------------------------------------------
# 客户端
# ---------------------------------------------------------------------------


class AmapClient:
    """一个进程共用一个实例即可（httpx.AsyncClient 内部有连接池）。"""

    def __init__(self, key: str | None = None, timeout: int | None = None) -> None:
        self._key = key or os.environ.get("TPA_AMAP_KEY", "")
        self._timeout = float(timeout or os.environ.get("TPA_AMAP_TIMEOUT", "8") or 8)
        self._client: httpx.AsyncClient | None = None

    @property
    def key(self) -> str:
        if not self._key:
            raise AmapError("UPSTREAM_AUTH_FAILED", "未配置 TPA_AMAP_KEY")
        return self._key

    async def _http(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=BASE_URL,
                timeout=httpx.Timeout(self._timeout),
                headers={"User-Agent": "tpa-mcp/1.0"},
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()

    async def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        """只对网络类错误额外重试 1 次（15.1）。"""
        query = {"key": self.key, **params}
        attempts = 2
        last_error: AmapError | None = None
        client = await self._http()

        for attempt in range(1, attempts + 1):
            try:
                resp = await client.get(path, params=query)
            except httpx.TimeoutException as exc:
                last_error = AmapError("TIMEOUT", "高德接口超时")
                logger.warning("高德超时 %s (第 %s 次)", path, attempt)
                if attempt == attempts:
                    raise last_error from exc
                continue
            except httpx.HTTPError as exc:
                last_error = AmapError("UPSTREAM_ERROR", f"高德请求失败: {exc}")
                logger.warning("高德请求失败 %s (第 %s 次): %s", path, attempt, exc)
                if attempt == attempts:
                    raise last_error from exc
                continue

            if resp.status_code != 200:
                raise AmapError("UPSTREAM_ERROR", f"高德返回 HTTP {resp.status_code}")

            try:
                body = resp.json()
            except ValueError as exc:
                raise AmapError("UPSTREAM_ERROR", "高德返回的不是 JSON") from exc

            self._raise_for_status(body)
            return body

        raise last_error or AmapError("UPSTREAM_ERROR", "高德请求失败")

    @staticmethod
    def _raise_for_status(body: dict[str, Any]) -> None:
        status = str(body.get("status", "")).strip()
        info = str(body.get("info", "")).strip()
        infocode = str(body.get("infocode", "")).strip()
        # 成功判定要宽容：高德不同接口/不同情况下 info 会写成 "OK" 或 "ok"，
        # 只要 status=1 且（info 大小写不敏感地等于 ok 或 infocode=10000）就算成功。
        if status == "1" and (info.lower() == "ok" or infocode == "10000"):
            return
        code = INFOCODE_TO_ERROR.get(infocode, "UPSTREAM_ERROR")
        message = f"高德接口返回 {info or '未知错误'}"
        if infocode:
            message += f"（infocode={infocode}）"
        if code == "UPSTREAM_AUTH_FAILED":
            # 15.3：Key 无效不重试，打 ERROR
            logger.error("高德鉴权失败，检查 TPA_AMAP_KEY 与 API 权限：%s", message)
        raise AmapError(code, message)

    # ---------------------------------------------------------------- 天气

    async def weather_live(self, city: str) -> dict[str, Any]:
        body = await self._get(
            "/v3/weather/weatherInfo", {"city": city, "extensions": "base"}
        )
        lives = body.get("lives") or []
        if not lives:
            raise AmapError("NOT_FOUND", f"查不到城市 {city} 的实时天气")
        live = lives[0]
        adcode = to_str(live.get("adcode"))
        cityname = to_str(live.get("city"))
        temperature = to_int(live.get("temperature"), "temperature")
        if not adcode or temperature is None:
            raise AmapError("NOT_FOUND", f"查不到城市 {city} 的实时天气")
        return {
            "city": cityname,
            "adcode": adcode,
            "province": to_str(live.get("province")),
            "weather": to_str(live.get("weather")),
            "temperature_c": temperature,
            "wind_direction": to_str(live.get("winddirection")),
            "wind_power": to_str(live.get("windpower")),
            "humidity": to_int(live.get("humidity"), "humidity"),
            "report_time": _with_offset(to_str(live.get("reporttime"))),
        }

    async def weather_forecast(self, city: str, days: int) -> dict[str, Any]:
        body = await self._get(
            "/v3/weather/weatherInfo", {"city": city, "extensions": "all"}
        )
        forecasts = body.get("forecasts") or []
        if not forecasts:
            raise AmapError("NOT_FOUND", f"查不到城市 {city} 的天气预报")
        forecast = forecasts[0]
        casts = forecast.get("casts") or []
        if not casts:
            raise AmapError("NOT_FOUND", f"城市 {city} 暂无预报数据")
        adcode = to_str(forecast.get("adcode"))
        if not adcode:
            raise AmapError("NOT_FOUND", f"查不到城市 {city} 的 adcode")
        return {
            "city": to_str(forecast.get("city")) or to_str(forecast.get("province")),
            "adcode": adcode,
            "report_time": _with_offset(to_str(forecast.get("reporttime"))),
            "forecast": [
                {
                    "date": to_str(cast.get("date")),
                    "day_weather": to_str(cast.get("dayweather")),
                    "night_weather": to_str(cast.get("nightweather")),
                    "day_temp_c": to_int(cast.get("daytemp"), "daytemp"),
                    "night_temp_c": to_int(cast.get("nighttemp"), "nighttemp"),
                    "day_wind": to_str(cast.get("daywind")),
                    "day_power": to_str(cast.get("daypower")),
                }
                for cast in casts[:days]
            ],
        }

    # ---------------------------------------------------------------- POI

    async def place_text(
        self, keywords: str, city: str | None, page_size: int
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "keywords": keywords,
            "offset": page_size,
            "page": 1,
            "extensions": "all",  # 才有 biz_ext（评分/人均）
        }
        if city:
            params["city"] = city
            params["citylimit"] = "true"
        body = await self._get("/v3/place/text", params)
        total = to_int(body.get("count"), "count") or 0
        raw_pois = body.get("pois") or []
        if total == 0 or not raw_pois:
            raise AmapError("NOT_FOUND", f"没有找到与「{keywords}」匹配的地点")

        pois = []
        for poi in raw_pois[:page_size]:
            biz = poi.get("biz_ext") or {}
            pois.append(
                {
                    "id": to_str(poi.get("id")),
                    "name": to_str(poi.get("name")),
                    "type": to_str(poi.get("type")),
                    "address": to_str(poi.get("address")),
                    "location": _normalize_location(poi.get("location")),
                    "city": to_str(poi.get("cityname")),
                    "district": to_str(poi.get("adname")),
                    "rating": to_str(biz.get("rating")) if isinstance(biz, dict) else None,
                    "cost_cent": to_cent(biz.get("cost")) if isinstance(biz, dict) else None,
                }
            )
        return {"total": total, "pois": pois}

    # ---------------------------------------------------------------- 地理编码

    async def geocode(self, address: str, city: str | None) -> dict[str, Any]:
        params: dict[str, Any] = {"address": address}
        if city:
            params["city"] = city
        body = await self._get("/v3/geocode/geo", params)
        geocodes = body.get("geocodes") or []
        if not geocodes:
            raise AmapError("NOT_FOUND", f"无法解析地址「{address}」")
        geo = geocodes[0]
        location = _normalize_location(geo.get("location"))
        if not location:
            raise AmapError("NOT_FOUND", f"无法解析地址「{address}」的坐标")
        return {
            "formatted_address": to_str(geo.get("formatted_address")),
            "location": location,
            "adcode": to_str(geo.get("adcode")),
            "citycode": to_str(geo.get("citycode")),
            "city": to_str(geo.get("city")),
            "district": to_str(geo.get("district")),
            "level": to_str(geo.get("level")),
        }

    # ---------------------------------------------------------------- 路径规划

    async def route(self, mode: str, origin: str, destination: str) -> dict[str, Any]:
        origin = validate_location(origin, "origin")
        destination = validate_location(destination, "destination")

        if mode == "transit":
            # 15.10：transit 结构差异最大，Demo 先不做
            raise AmapError("NOT_IMPLEMENTED", "暂不支持公交路径规划，请用 driving 或 walking")

        # 15.7 超长距离保护：先用直线距离粗判，超了就不打上游（省配额也省 15 秒）
        if mode == "walking" and _approx_distance_m(origin, destination) > 300_000:
            raise AmapError("INVALID_ARGUMENT", "该距离不适合步行")

        path = "/v3/direction/driving" if mode == "driving" else "/v3/direction/walking"
        body = await self._get(
            path, {"origin": origin, "destination": destination, "extensions": "base"}
        )
        route = body.get("route") or {}
        paths = route.get("paths") or []
        if not paths:
            raise AmapError("NOT_FOUND", "没有可用的路线")

        best = paths[0]
        distance_m = to_int(best.get("distance"), "distance")
        duration_s = to_int(best.get("duration"), "duration")
        if mode == "walking" and distance_m is not None and distance_m > 300_000:
            raise AmapError("INVALID_ARGUMENT", "该距离不适合步行")

        steps = []
        for step in (best.get("steps") or [])[:50]:
            steps.append(
                {
                    "instruction": to_str(step.get("instruction")),
                    "road": to_str(step.get("road")),
                    "distance_m": to_int(step.get("distance"), "step.distance"),
                    "duration_s": to_int(step.get("duration"), "step.duration"),
                }
            )

        return {
            "mode": mode,
            "distance_m": distance_m,
            "duration_s": duration_s,
            "taxi_cost_cent": to_cent(route.get("taxi_cost")),
            "steps": steps,
        }


def _with_offset(report_time: str | None) -> str | None:
    """高德给的是 `2025-03-18 14:00:00`，补 `+08:00` 并换成 ISO 的 T 分隔。"""
    if not report_time:
        return None
    text = report_time.strip().replace(" ", "T")
    if text.endswith(("Z", "+08:00")):
        return text
    return f"{text}+08:00"


def _approx_distance_m(origin: str, destination: str) -> float:
    """直线距离粗算（等距圆柱近似，GCJ-02 上够用），只用于"要不要打上游"的前置判断。"""
    try:
        lng1, lat1 = (float(x) for x in origin.split(","))
        lng2, lat2 = (float(x) for x in destination.split(","))
    except (TypeError, ValueError):
        return 0.0
    import math

    rad = math.radians
    x = rad(lng2 - lng1) * math.cos(rad((lat1 + lat2) / 2))
    y = rad(lat2 - lat1)
    return math.hypot(x, y) * 6_371_000


def get_client() -> AmapClient:
    return AmapClient()
