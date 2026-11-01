#!/usr/bin/env python3
"""Releaseのソースから作ったWindows配布ZIPを、展開後の状態で検証する。AVX512版はIntel SDEで実行する。"""
import gzip
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import threading
import time
import zipfile

ROOT = Path.cwd()
SOURCE = ROOT / "work/NAGISA_V4"
RECORDS = ROOT / "validation"
ARCHIVE_SHA = "95afa6795c1c2531e2963b5ef7ec805edba0c8a458afbc4e30ff28e3c1fb55d9"
NN_SHA = "39dd05367e1b66c8a12d41aefb9ca81070dc643060bcb5cb3306043f118e7415"
PROGRESS_SHA = "e7ed0eef88868335f9a46c58a121dccb5ad82a5eb1c8ee12de90365ab351e37d"
SOURCE_URL = ("https://github.com/keinoda/YaneuraOu/releases/download/nagisa-v4/"
              "NAGISA_V4-source-20261030-tournament.tar.gz")
# 本家V9.90開発版の配布スクリプトの4指定に、本家で採用済みのUSE_FINNY_RESETを加える。
FLAGS = ["-DHASH_KEY_BITS=128", "-DTT_CLUSTER_SIZE=4", "-DUSE_LAZY_EVALUATE",
         "-DUSE_FINNY_TABLES", "-DUSE_FINNY_RESET"]
EXPERIMENTAL = ["NNUE_FT_SPECIALIZED", "NNUE_FT_REGS", "NNUE_FINNY_CANCEL", "NNUE_SFNN_FUSED_FT",
                "NNUE_FINNY_MASK_DIFF", "NNUE_FT_COMPACT"]
# FT幅2304では、AVX512だけ本家の24レジスタ経路になり、AVX2は従来の16レジスタのまま。
FT_REGISTERS = {"AVX2": 16, "AVX512": 24}
MOVE = re.compile(r"(?:[1-9][a-i][1-9][a-i]\+?|[PLNSGBR]\*[1-9][a-i])\Z")


def sha256(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            result.update(block)
    return result.hexdigest()


def prepare():
    RECORDS.mkdir()
    (ROOT / "work").mkdir()
    archive = ROOT / "source.tar.gz"
    if sha256(archive) != ARCHIVE_SHA:
        raise ValueError("Releaseから取得したソースのSHA-256が一致しません")
    with tarfile.open(archive) as tar:
        for member in tar.getmembers():
            if not member.isfile() or not member.name.startswith("NAGISA_V4/") or ".." in Path(member.name).parts:
                raise ValueError("ソースアーカイブに想定外のエントリーがあります")
        tar.extractall(ROOT / "work")
    if sha256(SOURCE / "eval/nn.bin") != NN_SHA or sha256(SOURCE / "eval/progress.bin") != PROGRESS_SHA:
        raise ValueError("評価データのSHA-256が一致しません")
    (RECORDS / "source.json").write_text(json.dumps({"url": SOURCE_URL, "sha256": ARCHIVE_SHA}, indent=2))


class Engine:
    def __init__(self, runtime, log_name="usi.log", sde=None):
        self.log = (RECORDS / log_name).open("w", encoding="utf-8")
        # SDEのエミュレーションは遅いため、応答期限を延ばす。
        self.timeout = 1800 if sde else 120
        command = [str(runtime / "NAGISA_V4.exe")]
        if sde:
            # Skylake-X相当のCPUとして実行し、想定外の命令があれば失敗させる。
            command = [str(sde), "-skx", "--"] + command
        environment = os.environ.copy()
        # MSYS2のDLL探索パスに依存せず、展開したZIPだけで動くことを確かめる。
        if sys.platform == "win32":
            system = Path(environment["SYSTEMROOT"])
            environment["PATH"] = str(system / "System32") + os.pathsep + str(system)
        self.process = subprocess.Popen(command, cwd=runtime,
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                                        errors="replace", bufsize=1, env=environment)
        self.lines = queue.Queue()
        self.reader = threading.Thread(target=self.read_output, daemon=True)
        self.reader.start()

    def read_output(self):
        try:
            for line in self.process.stdout:
                self.lines.put(line.rstrip("\r\n"))
        finally:
            self.lines.put(None)

    def send(self, command):
        self.log.write("> " + command + "\n")
        self.log.flush()
        self.process.stdin.write(command + "\n")
        self.process.stdin.flush()

    def until(self, predicate):
        deadline = time.monotonic() + self.timeout
        found = []
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("エンジンの応答期限を超過しました")
            line = self.lines.get(timeout=remaining)
            if line is None:
                raise RuntimeError(f"応答前にエンジンが終了しました: {self.process.poll()}")
            self.log.write(line + "\n")
            found.append(line)
            if predicate(line):
                self.log.flush()
                return found

    def ready(self):
        self.send("usi")
        usi = self.until(lambda line: line == "usiok")
        if "id author nagisa" not in usi or not any(line.startswith("id name NAGISA_V4") for line in usi):
            raise AssertionError("エンジンの識別情報が一致しません")
        if not any("FV_SCALE type spin default 28" in line for line in usi):
            raise AssertionError("FV_SCALEの既定値が28ではありません")
        self.send("setoption name Threads value 1")
        self.send("setoption name USI_Hash value 64")
        self.send("isready")
        lines = self.until(lambda line: line == "readyok")
        if any(re.search(r"warning|error|failed|mismatch|falling back", line, re.I) for line in lines):
            raise AssertionError("評価データの読み込みに警告または失敗があります")
        if not any("loading progress file :" in line and "<internal>" not in line for line in lines):
            raise AssertionError("独自progress.binの読み込みを確認できません")
        self.send("getoption FV_SCALE")
        value = self.until(lambda line: "Options[FV_SCALE]" in line)[-1]
        if not re.search(r"=\s*28\s*$", value):
            raise AssertionError("FV_SCALEの実効値が28ではありません")

    def evaluate(self, position):
        self.send("position " + position)
        self.send("e")
        return int(self.until(lambda line: line.startswith("eval = "))[-1].split("=")[1])

    def search(self, position):
        self.send("position " + position)
        self.send("moves")
        self.send("e")
        lines = self.until(lambda line: line.startswith("eval = "))
        legal = {move for line in lines[:-1] for move in line.split() if MOVE.fullmatch(move)}
        self.send("go nodes 100000")
        lines = self.until(lambda line: line.startswith("bestmove "))
        best = lines[-1].split()[1]
        counts = [int(match[1]) for line in lines for match in [re.search(r"\bnodes (\d+)", line)] if match]
        if best not in legal or not counts or max(counts) == 0:
            raise AssertionError("合法手を返す実探索を確認できません")
        return {"bestmove": best, "nodes": max(counts), "position": position}

    def close(self):
        if self.process.poll() is None:
            self.send("quit")
            try:
                self.process.wait(timeout=120)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        self.log.close()
        return self.process.returncode


def check_build(cpu):
    log = (RECORDS / "build.log").read_text(encoding="utf-8", errors="replace")
    line = next(line for line in log.splitlines() if line.startswith("clang++ ") and "-c main.cpp" in line)
    flags = shlex.split(line)
    for flag in FLAGS + ["-DFOR_TOURNAMENT"]:
        if flag not in flags:
            raise AssertionError("ビルド指定が不足しています: " + flag)
    arguments = []
    index = 0
    while index < len(flags):
        if flags[index] == "-o":
            index += 2
            continue
        if flags[index] not in {"-c", "-MMD", "-MP"}:
            arguments.append(flags[index])
        index += 1
    macros = subprocess.check_output(arguments + ["-E", "-dM"], cwd=SOURCE / "source", text=True)
    (RECORDS / "macros.txt").write_text(macros)
    definitions = {line.split()[1]: " ".join(line.split()[2:]) for line in macros.splitlines() if line.startswith("#define ")}
    expected = {"HASH_KEY_BITS": "128", "TT_CLUSTER_SIZE": "4", "USE_LAZY_EVALUATE": "1", "USE_FINNY_TABLES": "1",
                "USE_FINNY_RESET": "1", "FOR_TOURNAMENT": "1", "NNUE_SFNN_HAND_BUCKETS": "1",
                "NNUE_SFNN_KING_BUCKETS": "1", "NNUE_SFNN_PROGRESS_BUCKETS": "8"}
    expected["USE_AVX512" if cpu == "AVX512" else "USE_AVX2"] = "1"
    for key, value in expected.items():
        if definitions.get(key) != value:
            raise AssertionError(f"実効設定が一致しません: {key}={definitions.get(key)}")
    for key in EXPERIMENTAL + (["USE_VNNI"] if cpu == "AVX512" else ["USE_AVX512"]):
        if key in definitions:
            raise AssertionError("想定外の指定が有効です: " + key)
    probe_dir = ROOT / "ft-register-probe"
    probe_dir.mkdir()
    probe = probe_dir / "probe.cpp"
    probe.write_text('#include "config.h"\n#include "eval/nnue/nnue_feature_transformer.h"\n'
                     "static_assert(YaneuraOu::Eval::NNUE::kTransformedFeatureDimensions == 2304, \"FT width\");\n"
                     f"static_assert(YaneuraOu::Eval::NNUE::kNumRegs == {FT_REGISTERS[cpu]}, \"FT tile registers\");\n")
    probe_arguments = [x for x in arguments if x != "main.cpp"]
    subprocess.run(probe_arguments + ["-I", str(SOURCE / "source"), "-fsyntax-only", str(probe)],
                   cwd=SOURCE / "source", check=True)
    imports = subprocess.check_output(["objdump", "-p", str(SOURCE / "NAGISA_V4.exe")], text=True)
    (RECORDS / "pe-imports.txt").write_text(imports)
    dlls = re.findall(r"DLL Name:\s*(\S+)", imports)
    if any(re.match(r"lib(?:stdc\+\+|gcc|winpthread|ssp|gomp|atomic|c\+\+)", dll, re.I) for dll in dlls):
        raise AssertionError("配布物に含まれないランタイムDLLへの依存があります")
    return {"compile_command": line, "dlls": dlls, "target_cpu": cpu, "extra_cppflags": FLAGS,
            "macros": expected, "ft_tile_registers": FT_REGISTERS[cpu], "progress_buckets": 8, "king_buckets": 1}


def check_unused_ninth(runtime, reference, sde):
    scratch = ROOT / "unused-ninth-runtime"
    shutil.copytree(runtime, scratch)
    nn = scratch / "eval/nn.bin"
    original_sha = sha256(nn)
    head_size = 4 + 16 * 4 + 2304 * 16 + 64 * 4 + 32 * 64 + 4 + 64
    with nn.open("r+b") as stream:
        # 構造ハッシュを残して9番目の重みを0にし、評価値へ影響しないことを確認する。
        stream.seek(-head_size + 4, 2)
        stream.write(bytes(head_size - 4))
    mutated_sha = sha256(nn)
    if original_sha != NN_SHA or original_sha == mutated_sha:
        raise AssertionError("9番目の重みを変更する回帰検証の入力が不正です")
    engine = Engine(scratch, "unused-ninth-usi.log", sde)
    try:
        engine.ready()
        for item in reference:
            if engine.evaluate(item["position"]) != item["score"]:
                raise AssertionError("9番目の重みが評価値へ影響しています: " + item["position"])
    finally:
        exit_code = engine.close()
    if exit_code != 0:
        raise AssertionError("9番目の不使用を検証したエンジンが正常終了しませんでした")
    return {"evaluation_matches": len(reference), "original_sha256": original_sha,
            "mutated_sha256": mutated_sha, "engine_exit_code": exit_code}


def find_sde():
    found = [path for path in [ROOT / "sde/sde.exe", ROOT / "sde/sde64.exe"] if path.exists()]
    if not found:
        raise FileNotFoundError("AVX512の検証に使うIntel SDEが見つかりません")
    return found[0]


def verify(cpu):
    if sys.platform != "win32":
        raise RuntimeError("この最終検証はWindows上で実行してください")
    build = check_build(cpu)
    sde = find_sde() if cpu == "AVX512" else None
    build["sde"] = f"{sde.name} -skx" if sde else None
    artifacts = ROOT / "artifacts"
    artifacts.mkdir()
    name = "NAGISA_V4-Windows-" + cpu
    archive = artifacts / (name + ".zip")
    files = ["NAGISA_V4.exe", "engine_name.txt", "LICENSE", "eval/nn.bin", "eval/progress.bin", "eval/eval_options.txt"]
    expected = {file: sha256(SOURCE / file) for file in files}
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6,
                         strict_timestamps=False) as zipped:
        for file in files:
            zipped.write(SOURCE / file, name + "/" + file)
    unpacked = ROOT / "unpacked"
    with zipfile.ZipFile(archive) as zipped:
        if set(zipped.namelist()) != {name + "/" + file for file in files}:
            raise AssertionError("配布ZIPのファイル一覧が一致しません")
        zipped.extractall(unpacked)
    runtime = unpacked / name
    for file, digest in expected.items():
        if sha256(runtime / file) != digest:
            raise AssertionError("展開後のSHA-256が一致しません: " + file)
    reference_path = Path(__file__).with_name("evaluation_reference.json.gz")
    reference = json.loads(gzip.decompress(reference_path.read_bytes()))
    engine = Engine(runtime, sde=sde)
    result = {"passed": False, "target_cpu": cpu, "build": build, "file_sha256": expected, "searches": []}
    try:
        engine.ready()
        for item in reference:
            actual = engine.evaluate(item["position"])
            if actual != item["score"]:
                raise AssertionError(f"Linux版と評価が一致しません: {actual} != {item['score']}; {item['position']}")
        result["evaluation_matches"] = len(reference)
        for item in reference[:5]:
            result["searches"].append(engine.search(item["position"]))
        engine.send("setoption name Threads value 2")
        engine.send("isready")
        engine.until(lambda line: line == "readyok")
        result["searches"].append(engine.search("startpos"))
        engine.send("position startpos")
        engine.send("go perft 4")
        count = int(engine.until(lambda line: "Nodes searched:" in line)[-1].split(":")[-1])
        if count != 719731:
            raise AssertionError(f"perft(4)が一致しません: {count}")
        result["perft4"] = count
        result["unused_ninth"] = check_unused_ninth(runtime, reference, sde)
        result["archive_sha256"] = sha256(archive)
        result["archive_bytes"] = archive.stat().st_size
        result["passed"] = True
    except Exception as error:
        result["error"] = str(error)
        raise
    finally:
        result["engine_exit_code"] = engine.close()
        if result["engine_exit_code"] != 0:
            result["passed"] = False
        (RECORDS / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if not result["passed"]:
        raise SystemExit(1)
    print(json.dumps({key: value for key, value in result.items() if key not in {"build", "searches", "file_sha256"}}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    if sys.argv[1:] == ["prepare"]:
        prepare()
    elif len(sys.argv) == 3 and sys.argv[1] == "verify" and sys.argv[2] in FT_REGISTERS:
        verify(sys.argv[2])
    else:
        raise SystemExit("prepare または verify AVX2|AVX512 を指定してください")
