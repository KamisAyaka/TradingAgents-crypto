"""一键启动所有数据抓取 runner（Binance / Odaily / Longform）。"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from typing import Dict, List, Tuple


# 各 runner 的启动命令（按默认依赖顺序排序：Binance → Odaily → Longform）
RUNNER_ORDER = ["binance", "odaily", "longform"]
RUNNER_COMMANDS: Dict[str, List[str]] = {
    "binance": [sys.executable, "-m", "fetchers.binance_runner"],
    "odaily": [sys.executable, "-m", "fetchers.odaily_runner"],
    "longform": [sys.executable, "-m", "fetchers.longform_runner"],
}


def _parse_targets() -> List[str]:
    env_value = os.getenv("RUN_FETCHERS", ",".join(RUNNER_ORDER))
    names = [item.strip().lower() for item in env_value.split(",") if item.strip()]
    if not names:
        return list(RUNNER_ORDER)
    unknown = [name for name in names if name not in RUNNER_COMMANDS]
    if unknown:
        raise ValueError(f"Unknown fetcher(s): {', '.join(unknown)}")
    # 保持依赖顺序：Binance -> Odaily -> Longform
    ordered = [name for name in RUNNER_ORDER if name in names]
    return ordered


def _launch_process(name: str, cmd: List[str]) -> subprocess.Popen:
    print(f"[run_all] 启动 {name} runner: {' '.join(cmd)}")
    return subprocess.Popen(cmd)


def main() -> None:
    targets = _parse_targets()
    processes: List[Tuple[str, subprocess.Popen]] = []

    try:
        for idx, name in enumerate(targets):
            proc = _launch_process(name, RUNNER_COMMANDS[name])
            processes.append((name, proc))
            # 若之后还有依赖项，给上游一点时间拉取数据
            if name in {"binance", "odaily"} and "longform" in targets[idx + 1 :]:
                time.sleep(5)

        print(
            "[run_all] 全部 runner 已启动，按 Ctrl+C 可结束（会发送 SIGTERM 并等待子进程退出）。"
        )
        while any(proc.poll() is None for _, proc in processes):
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[run_all] 捕获到 Ctrl+C，准备停止所有 runner ...")
    finally:
        for name, proc in processes:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                    print(f"[run_all] {name} runner 已退出。")
                except subprocess.TimeoutExpired:
                    proc.kill()
                    print(f"[run_all] 强制终止 {name} runner。")


if __name__ == "__main__":
    main()
