"""给 lerobot 的 OpenCVCamera 加「固定白平衡」开关。

背景：同一个相机，snap_once.py 拍出来正常（红块 H≈21），但 lerobot.record
推理时画面整体偏蓝（H≈100）。原因是自动白平衡（AWB）在两次开相机之间
漂到了不同色温。

用法：设环境变量后启动推理即可
    $env:LEROBOT_CAM_AWB = 'off'        # 关自动白平衡（用相机默认色温）
    $env:LEROBOT_CAM_AWB_TEMP = '4600'  # 可选：指定色温（K）
不设这个变量时行为完全不变。
"""

import io

P = r"D:\LeRobot\lerobot\src\lerobot\cameras\opencv\camera_opencv.py"

src = io.open(P, "r", encoding="utf-8", newline="").read()
NL = "\r\n" if "\r\n" in src else "\n"

if "LEROBOT_CAM_AWB" in src:
    print("补丁已存在，跳过")
    raise SystemExit(0)

anchor = "            self._validate_width_and_height()"
assert src.count(anchor) == 1, "找不到 _validate_width_and_height() 调用点"

inject = NL.join(
    [
        "            self._validate_width_and_height()",
        "",
        "            # [本地改动] 可选：固定白平衡 / 曝光，避免自动 AWB 在两次开相机",
        "            # 之间漂移导致画面偏色（训练和推理色温不一致会让策略判断错乱）。",
        "            #   LEROBOT_CAM_AWB=off      -> 关闭自动白平衡",
        "            #   LEROBOT_CAM_AWB_TEMP=4600 -> 指定色温（需同时关 AWB）",
        "            #   LEROBOT_CAM_AE=off        -> 关闭自动曝光",
        "            try:",
        "                import os as _os",
        "",
        "                _awb = _os.environ.get('LEROBOT_CAM_AWB', '').lower()",
        "                if _awb in ('off', '0', 'false'):",
        "                    _ok = self.videocapture.set(cv2.CAP_PROP_AUTO_WB, 0)",
        "                    _temp = _os.environ.get('LEROBOT_CAM_AWB_TEMP', '')",
        "                    if _temp:",
        "                        try:",
        "                            self.videocapture.set(cv2.CAP_PROP_WB_TEMPERATURE, float(_temp))",
        "                        except Exception:",
        "                            pass",
        "                    logging.info(f'{self} 已关闭自动白平衡 (set ok={_ok}, temp={_temp or \"默认\"})')",
        "                _ae = _os.environ.get('LEROBOT_CAM_AE', '').lower()",
        "                if _ae in ('off', '0', 'false'):",
        "                    self.videocapture.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)",
        "                    logging.info(f'{self} 已关闭自动曝光')",
        "            except Exception as _exc:",
        "                logging.warning(f'{self} 设置白平衡/曝光失败: {_exc}')",
    ]
)
src = src.replace(anchor, inject, 1)

io.open(P, "w", encoding="utf-8", newline="").write(src)
print("补丁已应用")
