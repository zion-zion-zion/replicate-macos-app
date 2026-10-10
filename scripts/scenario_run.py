import argparse
import datetime
import filecmp
import hashlib
import json
import os
import plistlib
import subprocess
from pathlib import Path

RUN_FILES = ("run.json", "stdout.txt", "stderr.txt")


def now():
    return datetime.datetime.now(datetime.timezone.utc)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_sha256(app):
    # 按相对路径计入目录、符号链接目标和文件内容，复制或解开归档后的同一份 .app 结果相同。
    entries = []
    for directory, dirnames, filenames in os.walk(app):
        base = Path(directory)
        for name in dirnames + filenames:
            path = base / name
            relative = path.relative_to(app).as_posix()
            if path.is_symlink():
                entries.append(f"l {relative} {os.readlink(path)}")
            elif path.is_dir():
                entries.append(f"d {relative}")
            else:
                entries.append(f"f {relative} {sha256(path)}")
    return hashlib.sha256("\n".join(sorted(entries)).encode()).hexdigest()


def write_run(out, run):
    (out / "run.json").write_text(json.dumps(run, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_info(app):
    path = app / "Contents" / "Info.plist"
    if not path.is_file():
        raise SystemExit(f"不是有效的 App bundle: {app}")
    return plistlib.loads(path.read_bytes())


def targets(project, root):
    ledger = json.loads((root / "feature-ledger.json").read_text(encoding="utf-8"))
    manifest = json.loads((root / "reference-manifest.json").read_text(encoding="utf-8"))
    original, reference = ledger["app"], manifest["reference"]
    if not reference.get("bundle_id") or not reference.get("artifact_path"):
        raise SystemExit("先在 reference-manifest.json 填写 reference.bundle_id 和 reference.artifact_path"
                         "（B 的 bundle identifier 和相对项目根目录的 .app 路径）")
    sides = {"original": (original["bundle_id"], Path(original["path"])),
             "replica": (reference["bundle_id"], project / reference["artifact_path"])}
    for side, (bundle_id, app) in sides.items():
        info = read_info(app)
        if info.get("CFBundleIdentifier") != bundle_id:
            raise SystemExit(f"{side}: {app} 的 CFBundleIdentifier 是 {info.get('CFBundleIdentifier')}，记录的是 {bundle_id}")
        if side == "original" and (info.get("CFBundleShortVersionString"), info.get("CFBundleVersion")) \
                != (original.get("version"), original.get("build")):
            raise SystemExit(f"原版 A 已变为 {info.get('CFBundleShortVersionString')}（{info.get('CFBundleVersion')}），"
                             f"功能清单记录的是 {original.get('version')}（{original.get('build')}）")
    return sides


def run_side(root, scenario, side, bundle_id, app, timeout):
    script = root / scenario["script"]
    info = read_info(app)
    app_sha256 = tree_sha256(app) if side == "replica" else None
    out = root / "evidence" / "runs" / scenario["id"] / f"{side}-{now().strftime('%Y%m%dT%H%M%S%fZ')}"
    out.mkdir(parents=True)
    argv = [str(script), bundle_id, str(app), str(out)]
    started = now()
    try:
        proc = subprocess.run(argv, cwd=root, capture_output=True, timeout=timeout,
                              env={**os.environ, "REPLICA_SIDE": side})
        exit_code, stdout, stderr, timed_out = proc.returncode, proc.stdout, proc.stderr, False
    except subprocess.TimeoutExpired as exc:
        # 超时也是一次运行结果，记录已有输出后按失败返回。
        exit_code, stdout, stderr, timed_out = None, exc.stdout or b"", exc.stderr or b"", True
    finished = now()
    (out / "stdout.txt").write_bytes(stdout)
    (out / "stderr.txt").write_bytes(stderr)
    outputs = sorted(str(path.relative_to(out)) for path in out.rglob("*")
                     if path.is_file() and str(path.relative_to(out)) not in RUN_FILES)
    run = {"scenario": scenario["id"], "side": side, "bundle_id": bundle_id, "app_path": str(app),
           "app_version": info.get("CFBundleShortVersionString"), "app_build": info.get("CFBundleVersion"),
           "app_sha256": app_sha256,
           "script": scenario["script"], "script_sha256": sha256(script), "argv": argv,
           "started_at": started.isoformat(), "finished_at": finished.isoformat(),
           "exit_code": exit_code, "timed_out": timed_out, "outputs": outputs}
    write_run(out, run)
    return out, run


def compare(results):
    (a_dir, a), (b_dir, b) = results["original"], results["replica"]
    left, right = set(a["outputs"]), set(b["outputs"])
    same = sorted(name for name in left & right
                  if filecmp.cmp(a_dir / name, b_dir / name, shallow=False))
    return {"identical": same, "different": sorted(left & right - set(same)),
            "only_original": sorted(left - right), "only_replica": sorted(right - left)}


def latest_original(root, scenario_id, script_sha):
    # 只运行 B 时，和 A 一侧当前脚本最近一次成功的运行比较；目录名以 UTC 时间结尾，按名称排序即按时间排序。
    for path in sorted((root / "evidence" / "runs" / scenario_id).glob("original-*/run.json"), reverse=True):
        run = json.loads(path.read_text(encoding="utf-8"))
        if run["exit_code"] == 0 and run["script_sha256"] == script_sha:
            return path.parent, run
    return None


def main():
    parser = argparse.ArgumentParser(
        description="对 A 和 B 运行 script 场景，运行记录写入 replica/evidence/runs/场景ID/。")
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("scenario_id")
    parser.add_argument("--side", choices=("original", "replica", "both"), default="both")
    parser.add_argument("--timeout", type=float, default=600, help="每一侧的超时秒数")
    args = parser.parse_args()
    project = args.project_dir.expanduser().resolve()
    root = project / "replica"
    scenarios = json.loads((root / "scenarios.json").read_text(encoding="utf-8"))["scenarios"]
    scenario = next((item for item in scenarios if item.get("id") == args.scenario_id), None)
    if scenario is None:
        raise SystemExit(f"scenarios.json 中没有 {args.scenario_id}")
    if scenario.get("kind") != "script":
        raise SystemExit(f"{args.scenario_id} 的 kind 是 {scenario.get('kind')}，运行器只执行 script 场景")
    script = root / str(scenario.get("script"))
    if not script.is_file() or not os.access(script, os.X_OK):
        raise SystemExit(f"脚本不存在或不可执行: {script}")
    sides = targets(project, root)
    chosen = ("original", "replica") if args.side == "both" else (args.side,)
    results = {side: run_side(root, scenario, side, *sides[side], args.timeout) for side in chosen}
    report = {"scenario": args.scenario_id, "runs": {
        side: {"evidence": {"kind": "run", "path": str((out / "run.json").relative_to(root))},
               "exit_code": run["exit_code"], "timed_out": run["timed_out"], "outputs": run["outputs"]}
        for side, (out, run) in results.items()}}
    pair = dict(results)
    if args.side == "replica":
        latest = latest_original(root, args.scenario_id, results["replica"][1]["script_sha256"])
        if latest is not None:
            pair["original"] = latest
    if len(pair) == 2:
        (original_dir, original), (out, run) = pair["original"], pair["replica"]
        report["compare"] = {"original_run": str((original_dir / "run.json").relative_to(root)),
                             **compare(pair)}
        # A 一侧运行失败时，比较结果只用于排查，不写进 B 的运行记录。
        if original["exit_code"] == 0:
            write_run(out, {**run, "compare": report["compare"]})
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if all(run["exit_code"] == 0 for _, run in results.values()) else 1)


if __name__ == "__main__":
    main()
