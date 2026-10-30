#!/usr/bin/env python3
"""Releaseのソースから作ったWindows配布ZIPを、展開後の状態で検証する。"""
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
ARCHIVE_SHA = "e59f7ea8999acc3150bb0101bbaa13f4d69f0c469160cf3b881edef4ea8ef7b1"
NN_SHA = "39dd05367e1b66c8a12d41aefb9ca81070dc643060bcb5cb3306043f118e7415"
PROGRESS_SHA = "e7ed0eef88868335f9a46c58a121dccb5ad82a5eb1c8ee12de90365ab351e37d"
SOURCE_URL = ("https://github.com/keinoda/YaneuraOu/releases/download/nagisa-v4/"
              "NAGISA_V4-source-20261030-tournament.tar.gz")
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
    def __init__(self, runtime, log_name="usi.log"):
        self.log = (RECORDS / log_name).open("w", encoding="utf-8")
        environment = os.environ.copy()
        # MSYS2のDLL探索パスに依存せず、展開したZIPだけで動くことを確かめる。
        if sys.platform == "win32":
            system = Path(environment["SYSTEMROOT"])
            environment["PATH"] = str(system / "System32") + os.pathsep + str(system)
        self.process = subprocess.Popen([str(runtime / "NAGISA_V4.exe")], cwd=runtime,
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
        deadline = time.monotonic() + 120
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


def check_build():
    log = (RECORDS / "build.log").read_text(encoding="utf-8", errors="replace")
    line = next(line for line in log.splitlines() if line.startswith("clang++ ") and "-c main.cpp" in line)
    flags = shlex.split(line)
    for flag in ["-DUSE_LAZY_EVALUATE", "-DHASH_KEY_BITS=128", "-DTT_CLUSTER_SIZE=4",
                 "-DUSE_FINNY_TABLES", "-DUSE_FINNY_RESET"]:
        if flag in flags:
            raise AssertionError("追加最適化が含まれています: " + flag)
    if "-DFOR_TOURNAMENT" not in flags:
        raise AssertionError("通常tournament版ではありません")
    arguments = []
    index = 0
    while index < len(flags):
        if flags[index] == "-o":
            index += 2
            continue
        if flags[index] not in {"-c", "-MMD", "-MP"}:
            arguments.append(flags[index])
        index += 1
    arguments += ["-E", "-dM"]
    macros = subprocess.check_output(arguments, cwd=SOURCE / "source", text=True)
    (RECORDS / "macros.txt").write_text(macros)
    definitions = {line.split()[1]: " ".join(line.split()[2:]) for line in macros.splitlines() if line.startswith("#define ")}
    if definitions.get("HASH_KEY_BITS") != "64" or definitions.get("TT_CLUSTER_SIZE") != "3" or "USE_LAZY_EVALUATE" in definitions:
        raise AssertionError("標準のHASH・TT・評価設定ではありません")
    for key, expected in {"NNUE_SFNN_HAND_BUCKETS": "1", "NNUE_SFNN_KING_BUCKETS": "1", "NNUE_SFNN_PROGRESS_BUCKETS": "8"}.items():
        if definitions.get(key) != expected:
            raise AssertionError("進行度だけで8バケットを選ぶ設定ではありません: " + key)
    imports = subprocess.check_output(["objdump", "-p", str(SOURCE / "NAGISA_V4.exe")], text=True)
    (RECORDS / "pe-imports.txt").write_text(imports)
    dlls = re.findall(r"DLL Name:\s*(\S+)", imports)
    if any(re.match(r"lib(?:stdc\+\+|gcc|winpthread|ssp|gomp|atomic|c\+\+)", dll, re.I) for dll in dlls):
        raise AssertionError("配布物に含まれないランタイムDLLへの依存があります")
    return {"compile_command": line, "dlls": dlls, "HASH_KEY_BITS": 64, "TT_CLUSTER_SIZE": 3,
            "USE_LAZY_EVALUATE": False, "FOR_TOURNAMENT": True, "progress_buckets": 8, "king_buckets": 1}


def check_unused_ninth(runtime, reference):
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
    engine = Engine(scratch, "unused-ninth-usi.log")
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


def verify():
    if sys.platform != "win32":
        raise RuntimeError("この最終検証はWindows上で実行してください")
    build = check_build()
    artifacts = ROOT / "artifacts"
    artifacts.mkdir()
    archive = artifacts / "NAGISA_V4-Windows-AVX2.zip"
    files = ["NAGISA_V4.exe", "engine_name.txt", "LICENSE", "eval/nn.bin", "eval/progress.bin", "eval/eval_options.txt"]
    expected = {name: sha256(SOURCE / name) for name in files}
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6,
                         strict_timestamps=False) as zipped:
        for name in files:
            zipped.write(SOURCE / name, "NAGISA_V4-Windows-AVX2/" + name)
    unpacked = ROOT / "unpacked"
    with zipfile.ZipFile(archive) as zipped:
        if set(zipped.namelist()) != {"NAGISA_V4-Windows-AVX2/" + name for name in files}:
            raise AssertionError("配布ZIPのファイル一覧が一致しません")
        zipped.extractall(unpacked)
    runtime = unpacked / "NAGISA_V4-Windows-AVX2"
    for name, digest in expected.items():
        if sha256(runtime / name) != digest:
            raise AssertionError("展開後のSHA-256が一致しません: " + name)
    reference_path = Path(__file__).with_name("evaluation_reference.json.gz")
    reference = json.loads(gzip.decompress(reference_path.read_bytes()))
    engine = Engine(runtime)
    result = {"passed": False, "build": build, "file_sha256": expected, "searches": []}
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
        result["unused_ninth"] = check_unused_ninth(runtime, reference)
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
    if len(sys.argv) != 2 or sys.argv[1] not in {"prepare", "verify"}:
        raise SystemExit("prepare または verify を指定してください")
    {"prepare": prepare, "verify": verify}[sys.argv[1]]()
