#!/usr/bin/env python3
"""Run the opt-in comparison. Only fixed-schema, minimized results are written."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import selectors
import shutil
import signal
import subprocess
import tarfile
import tempfile
import time
import xml.etree.ElementTree as ET

from telemetry import ComparisonError, ZipkinReceiver, analyze_spans

ARCHIVE_URL = ("https://archive.apache.org/dist/shardingsphere/5.5.3/"
               "apache-shardingsphere-5.5.3-shardingsphere-agent-bin.tar.gz")
ARCHIVE_SHA512 = ("6538bf650cbdb1813814e1922b6c2072246c4595cb07322f793d5592c86be8759"
                  "49529ab6a00553c15f72a0b17e2d23628f6e8b5da9fb189a72ce8c4cfb37839")
ARCHIVE_BYTES = 46_741_869
TEST_CLASS = "io.github.ym0506.routecontract.experiments.agentcomparison.AgentComparisonMySqlTest"
ORACLE = {"schemaVersion": 1, "operations": 20, "logicalStatements": 40,
          "controlExpectedAttempts": 20, "fanOutExpectedAttempts": 40,
          "expectedPhysicalAttempts": 60, "proxyObservedAttempts": 60,
          "routeContractObservedAttempts": 60, "forcedFanOutPairs": 20,
          "uniqueRouteSignatures": 1}


def run_capped(command, cwd, environment, label, timeout=1200):
    """Retain process output only in bounded memory, including on test failure."""
    process = subprocess.Popen(command, cwd=cwd, env=environment, stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               start_new_session=True)
    output = bytearray()
    selector = selectors.DefaultSelector()
    deadline = time.monotonic() + timeout
    try:
        os.set_blocking(process.stdout.fileno(), False)
        selector.register(process.stdout, selectors.EVENT_READ)
        while selector.get_map():
            if time.monotonic() >= deadline:
                raise ComparisonError(label + "_TIMEOUT")
            for key, _ in selector.select(0.25):
                chunk = os.read(key.fileobj.fileno(), 65536)
                if not chunk:
                    selector.unregister(key.fileobj)
                elif len(output) + len(chunk) > 8 * 1024 * 1024:
                    raise ComparisonError(label + "_OUTPUT_LIMIT")
                else:
                    output.extend(chunk)
        code = process.wait(timeout=max(0.1, deadline - time.monotonic()))
        if code:
            # Exception classes aid diagnosis without exposing SQL or exception messages.
            types = sorted(set(re.findall(rb"\b(?:java|org|io|com)\.[A-Za-z0-9_.]+(?:Exception|Error)\b", output)))
            print(json.dumps({"stage": label, "exitCode": code,
                              "exceptionTypes": [item.decode("ascii") for item in types[:12]]}))
            raise ComparisonError(label + "_FAILED")
        return bytes(output)
    finally:
        selector.close()
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=3)
        process.stdout.close()
        output.clear()


def prepare_agent(archive, destination):
    if archive.stat().st_size != ARCHIVE_BYTES:
        raise ComparisonError("ARCHIVE_SIZE")
    with archive.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha512").hexdigest()
    if digest != ARCHIVE_SHA512:
        raise ComparisonError("ARCHIVE_DIGEST")
    with tarfile.open(archive, "r:gz") as bundle:
        members = bundle.getmembers()
        if len(members) > 64 or sum(member.size for member in members) > 96 * 1024 * 1024:
            raise ComparisonError("ARCHIVE_LIMIT")
        for member in members:
            path = PurePosixPath(member.name)
            if (path.is_absolute() or ".." in path.parts or path.parts[:1] != ("agent",)
                    or not (member.isfile() or member.isdir()) or member.size > 32 * 1024 * 1024):
                raise ComparisonError("ARCHIVE_MEMBER")
            target = destination.joinpath(*path.parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with bundle.extractfile(member) as source, target.open("xb") as output:
                    shutil.copyfileobj(source, output)
    jar = destination / "agent/shardingsphere-agent-5.5.3.jar"
    if not jar.is_file():
        raise ComparisonError("AGENT_MISSING")
    return jar


def junit_counts(output):
    text = output.decode("utf-8", errors="replace")
    counts = {}
    for key in ("found", "skipped", "started", "aborted", "successful", "failed"):
        matches = re.findall(r"\[\s*(\d+) tests " + key + r"\s*\]", text)
        if len(matches) != 1:
            raise ComparisonError("JUNIT_SUMMARY")
        counts[key] = int(matches[0])
    if counts != {"found": 1, "skipped": 0, "started": 1, "aborted": 0, "successful": 1, "failed": 0}:
        raise ComparisonError("JUNIT_COUNTS")
    return counts


def runtime_artifacts(classpath):
    jars = [Path(item) for item in classpath.split(os.pathsep)]
    ss = [p for p in jars if "/org/apache/shardingsphere/" in p.as_posix()]
    rc = [p for p in jars if "/io/github/ym0506/" in p.as_posix() and p.name.startswith("routecontract-")]
    if not ss or any(not p.name.endswith("-5.5.3.jar") for p in ss):
        raise ComparisonError("SHARDINGSPHERE_RUNTIME")
    if len(rc) != 1 or rc[0].name != "routecontract-shardingsphere-5.5-0.1.3.jar":
        raise ComparisonError("ROUTECONTRACT_RUNTIME")
    selected = rc + [p for p in ss if p.name.startswith(("shardingsphere-infra-executor-",
                                                        "shardingsphere-infra-spi-"))]
    return {"shardingSphereJars": len(ss), "routeContractJars": len(rc),
            "selectedArtifacts": [{"name": p.name, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                                  for p in selected]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, help="reuse an ASF archive; exact SHA-512 is still required")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    result = root / "target/comparison"
    if result.exists():
        shutil.rmtree(result)
    env = os.environ.copy()
    for key in ("JAVA_TOOL_OPTIONS", "JDK_JAVA_OPTIONS", "_JAVA_OPTIONS", "JAVA_OPTS",
                "CLASSPATH", "MAVEN_OPTS", "MAVEN_ARGS"):
        env.pop(key, None)
    java = str(Path(env["JAVA_HOME"]) / "bin/java") if env.get("JAVA_HOME") else "java"
    version_output = run_capped([java, "-version"], root, env, "JAVA", 30).decode()
    version = re.search(r'version "([^"]+)"', version_output)
    if not version or not version[1].startswith("17."):
        raise ComparisonError("JAVA_VERSION")
    print("Compiling the standalone consumer (Agent is not attached).", flush=True)
    run_capped(["mvn", "--batch-mode", "--no-transfer-progress", "test-compile", "dependency:build-classpath",
                "-Dmdep.outputFile=target/classpath.txt"], root, env, "MAVEN")
    classpath = (root / "target/classpath.txt").read_text().strip()
    artifacts = runtime_artifacts(classpath)
    with tempfile.TemporaryDirectory(prefix="routecontract-agent-comparison-") as directory:
        temporary = Path(directory)
        archive = args.archive.resolve() if args.archive else temporary / "agent.tar.gz"
        if args.archive is None:
            print("Downloading the official Agent archive and verifying SHA-512.", flush=True)
            run_capped(["curl", "--fail", "--silent", "--show-error", "--location", "--max-time", "180",
                        "--max-filesize", str(ARCHIVE_BYTES), "--output", str(archive), ARCHIVE_URL],
                       root, env, "DOWNLOAD", 190)
        jar = prepare_agent(archive, temporary)
        oracle_file = temporary / "oracle.json"
        receiver = ZipkinReceiver()
        receiver.start()
        try:
            port = receiver.address[1]
            (temporary / "agent/conf/agent.yaml").write_text(f'''plugins:
  tracing:
    OpenTelemetry:
      props:
        otel.service.name: "routecontract-agent-comparison"
        otel.traces.exporter: "zipkin"
        otel.exporter.zipkin.endpoint: "http://127.0.0.1:{port}/api/v2/spans"
        otel.traces.sampler: "always_on"
        otel.bsp.schedule.delay: "100"
        otel.bsp.max.export.batch.size: "1"
        otel.bsp.max.queue.size: "2048"
''')
            print("Running one Agent-instrumented JUnit JVM against disposable MySQL.", flush=True)
            command = [java, f"-javaagent:{jar}", "-Dapi.version=1.44",
                       "-Dorg.slf4j.simpleLogger.defaultLogLevel=off",
                       f"-DroutecontractAgentEvidence={oracle_file}",
                       "-cp", str(root / "target/test-classes") + os.pathsep + classpath,
                       "org.junit.platform.console.ConsoleLauncher", "execute", "--select-class", TEST_CLASS,
                       "--details=summary", "--disable-ansi-colors", "--fail-if-no-tests"]
            output = run_capped(command, temporary, env, "JUNIT")
            counts = junit_counts(output)
            del output
        finally:
            receiver.stop()
        receiver.raise_if_failed()
        oracle = json.loads(oracle_file.read_text())
        if oracle != ORACLE:
            raise ComparisonError("ORACLE")
        observation = analyze_spans(receiver.snapshot())
        # Drop raw spans before writing any publishable output.
        receiver._spans.clear()

    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    dirty = bool(subprocess.check_output(["git", "status", "--porcelain", "--", "."], cwd=root, text=True))
    sources = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
               for p in sorted(root.rglob("*")) if p.is_file()
               and "target" not in p.relative_to(root).parts and "__pycache__" not in p.relative_to(root).parts}
    result.mkdir(parents=True)
    summary = {"schemaVersion": 1, "routeContract": "0.1.3", "shardingSphere": "5.5.3", "agent": "5.5.3",
               "agentArchiveSha512": ARCHIVE_SHA512, "java": version[1],
               "platform": platform.system() + "/" + platform.machine(),
               "mysqlImage": "mysql:8.4.11@sha256:b3b90af2a6552ae30c266fdb7d5dd55f3afb72404bb78d37fe8a23eb857fd3fb",
               "sampling": "always_on", "exporterQueueCapacity": 2048,
               "oracle": oracle, "agentObservation": observation, "junitConsoleCounts": counts,
               "runtimeArtifacts": artifacts, "sourceRevision": revision, "sourceDirty": dirty,
               "sourceSha256": sources, "workflowRunId": env.get("GITHUB_RUN_ID"),
               "workflowRunAttempt": env.get("GITHUB_RUN_ATTEMPT"),
               "pullRequestHeadRevision": env.get("EXPERIMENT_PR_HEAD") or None,
               "independentUserValidation": False}
    (result / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    suite = ET.Element("testsuite", name="AgentComparisonSanitizedConsoleResult", tests="1", failures="0", errors="0", skipped="0")
    ET.SubElement(suite, "testcase", classname=TEST_CLASS, name="sequentialOperationsExposeExpectedPhysicalAttemptCounts")
    ET.ElementTree(suite).write(result / "junit-sanitized.xml", encoding="utf-8", xml_declaration=True)
    print(json.dumps({"result": "VERIFIED_LOCAL_FIXTURE", "agentObservation": observation, "junitTests": 1}))


if __name__ == "__main__":
    try:
        main()
    except ComparisonError as error:
        print(str(error))
        raise SystemExit(1) from None
