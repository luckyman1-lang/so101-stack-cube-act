"""修 lerobot 在 Windows 上的 tempfile 独占 bug。

policies.py 的 PreTrainedConfig.from_pretrained：
    with tempfile.NamedTemporaryFile("w+") as f:   # Windows 下独占句柄
        config_file = f.name
        draccus.parse(..., config_file)            # 同一进程再 open -> PermissionError 13

改成：没有 cli_overrides 时直接用 draccus.decode 从 dict 构造（不落任何临时文件）。
有 overrides 时退回原逻辑（这种场景只在 CLI 显式覆盖时才出现）。
"""

import io

P = r"D:\LeRobot\lerobot\src\lerobot\configs\policies.py"

src = io.open(P, "r", encoding="utf-8", newline="").read()
NL = "\r\n" if "\r\n" in src else "\n"

if "本地改动] Windows 上 NamedTemporaryFile" in src:
    print("补丁已存在，跳过")
    raise SystemExit(0)

old = NL.join(
    [
        '        config.pop("type")',
        '        with tempfile.NamedTemporaryFile("w+") as f:',
        "            json.dump(config, f)",
        "            config_file = f.name",
        "            f.flush()",
        "",
        '            cli_overrides = policy_kwargs.pop("cli_overrides", [])',
        "            with draccus.config_type(\"json\"):",
        "                return draccus.parse(orig_config.__class__, config_file, args=cli_overrides)",
    ]
)

new = NL.join(
    [
        '        config.pop("type")',
        '        cli_overrides = policy_kwargs.pop("cli_overrides", [])',
        "        # [本地改动] Windows 上 NamedTemporaryFile 是独占句柄，draccus 再 open 它必然",
        "        # PermissionError [Errno 13]。没有 cli 覆盖时直接 decode dict，完全不落临时文件。",
        "        if not cli_overrides:",
        "            with draccus.config_type(\"json\"):",
        "                return draccus.decode(orig_config.__class__, config)",
        "        # 有 cli 覆盖时才走原路径（少见）",
        '        with tempfile.NamedTemporaryFile("w+", suffix=".json", delete=False) as f:',
        "            json.dump(config, f)",
        "            config_file = f.name",
        "            f.flush()",
        "        try:",
        "            with draccus.config_type(\"json\"):",
        "                return draccus.parse(orig_config.__class__, config_file, args=cli_overrides)",
        "        finally:",
        "            try:",
        "                import os as _os",
        "",
        "                _os.unlink(config_file)",
        "            except OSError:",
        "                pass",
    ]
)

assert old in src, "没找到要替换的代码块"
src = src.replace(old, new, 1)
io.open(P, "w", encoding="utf-8", newline="").write(src)
print("补丁已应用")
