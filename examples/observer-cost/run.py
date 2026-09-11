#!/usr/bin/env python3
"""Run a fixed, disposable-MySQL experiment; no application database configuration is accepted."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import statistics
import subprocess
import sys
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PACKAGE = Path("io/github/ym0506/routecontract/examples/firstproject")
CONDITIONS = ("absent", "idle", "checked")
MYSQL = "mysql:8.4.11@sha256:b3b90af2a6552ae30c266fdb7d5dd55f3afb72404bb78d37fe8a23eb857fd3fb"


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def run(command, log):
    with log.open("w") as output:
        subprocess.run(command, cwd=HERE, stdout=output, stderr=subprocess.STDOUT, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New directory outside the repository")
    parser.add_argument("--maven-repository", type=Path, help="Optional reusable public-dependency cache")
    parser.add_argument("--smoke", action="store_true", help="Short correctness check; never performance evidence")
    args = parser.parse_args()
    output = args.output.expanduser().resolve()
    if output.is_relative_to(ROOT) or output.exists():
        parser.error("Output must be a new directory outside the repository")
    java = str(Path(os.environ["JAVA_HOME"]) / "bin/java") if os.environ.get("JAVA_HOME") else shutil.which("java")
    maven = shutil.which("mvn")
    if not java or not maven:
        parser.error("Java 17 and Maven must be available")
    runtime = subprocess.check_output([java, "-version"], stderr=subprocess.STDOUT, text=True).strip()
    if not ('version "17.' in runtime or 'openjdk 17.' in runtime):
        parser.error("Select Java 17 with JAVA_HOME")
    subprocess.run(["docker", "info"], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
    output.mkdir(parents=True)
    sources = output / "sources" / PACKAGE
    sources.mkdir(parents=True)
    inputs = [HERE / "pom.xml", HERE / "run.py", HERE / "README.md"]
    fixture = ROOT / "examples/first-project/src/test/java" / PACKAGE
    for source in [fixture / "OrderFixture.java", fixture / "OrderRepository.java", *sorted((HERE / "src/main/java" / PACKAGE).glob("*.java"))]:
        shutil.copyfile(source, sources / source.name)
        inputs.append(source)
    inputs.append(ROOT / "examples/first-project/src/test/resources/sharding.yaml")
    settings = ROOT / "examples/public-maven-release-consumer/settings.xml"
    inputs.append(settings)
    repository = (args.maven_repository or output / "m2").expanduser().resolve()
    build = output / "build"
    classpath_file = output / "classpath.txt"
    receipt = {
        "status": "RUNNING", "startedAt": datetime.now(timezone.utc).isoformat(),
        "smoke": args.smoke, "sourceRevision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "sourceInputs": {str(p.relative_to(ROOT)): sha256(p) for p in inputs},
        "runtime": runtime, "os": platform.system() + " " + platform.release(),
        "architecture": platform.machine(), "logicalCpuCount": os.cpu_count(),
        "dockerServerVersion": subprocess.check_output(
            ["docker", "version", "--format", "{{.Server.Version}}"], text=True).strip(),
        "mysqlImage": MYSQL, "jmhVersion": "1.37", "threads": 1,
        "blocks": 1 if args.smoke else 3, "forksPerConditionAndQueryPerBlock": 1,
        "warmupIterations": 1 if args.smoke else 5,
        "measurementIterations": 1 if args.smoke else 5,
        "iterationSeconds": 1, "conditions": list(CONDITIONS), "completedCells": []
    }
    if platform.system() == "Darwin":
        receipt["cpuModel"] = subprocess.check_output(["sysctl", "-n", "machdep.cpu.brand_string"], text=True).strip()
        receipt["physicalMemoryBytes"] = int(subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True))
    write_json(output / "run.json", receipt)
    try:
        print("Resolving public dependencies and compiling JMH with shared fixture sources", flush=True)
        run([maven, "-B", "-ntp", "-s", str(settings), "-gs", str(settings),
             "-Dmaven.repo.local=" + str(repository),
             "-Dobserver.build.directory=" + str(build),
             "-Dobserver.source.directory=" + str(output / "sources"),
             "compile", "dependency:build-classpath", "-Dmdep.outputFile=" + str(classpath_file)],
            output / "build.log")
        paths = [Path(x) for x in classpath_file.read_text().strip().split(os.pathsep)]
        routecontract = [p for p in paths if p.name == "routecontract-shardingsphere-5.5-0.1.3.jar"]
        assert len(routecontract) == 1, "Expected exactly one published RouteContract JAR"
        assert len([p for p in paths if p.name.startswith("routecontract-")]) == 1
        for p in paths:
            if "org/apache/shardingsphere" in p.as_posix():
                assert p.parent.name == "5.5.3", p.name
        receipt["dependencies"] = {str(p.relative_to(repository)): sha256(p) for p in paths}
        write_json(output / "run.json", receipt)
        common = [str(build / "classes"), *[str(p) for p in paths if p not in routecontract]]
        collected = []
        for block in range(receipt["blocks"]):
            order = CONDITIONS[block:] + CONDITIONS[:block]
            for condition in order:
                label = f"block-{block + 1}-{condition}"
                cp = common if condition == "absent" else [*common, str(routecontract[0])]
                result_file = output / (label + ".json")
                print(f"Running {label}: equality and range, each in a fresh JVM", flush=True)
                command = [java, "-cp", os.pathsep.join(cp), "org.openjdk.jmh.Main", ".*ObserverCostBenchmark.*",
                           "-p", "condition=" + condition, "-p", "query=equality,range", "-t", "1", "-f", "1",
                           "-wi", str(receipt["warmupIterations"]), "-i", str(receipt["measurementIterations"]),
                           "-w", "1s", "-r", "1s", "-foe", "true", "-prof", "gc", "-rf", "json", "-rff", str(result_file),
                           "-jvmArgsAppend", "-Xms512m -Xmx512m -Dapi.version=1.44 -Dorg.slf4j.simpleLogger.defaultLogLevel=warn"]
                run(command, output / (label + ".log"))
                results = json.loads(result_file.read_text())
                assert len(results) == 2
                assert {r["params"]["query"] for r in results} == {"equality", "range"}
                log = (output / (label + ".log")).read_text()
                for result in results:
                    assert result["params"]["condition"] == condition
                    query = result["params"]["query"]
                    presence = "false providerCount=0" if condition == "absent" else "true providerCount=1"
                    assert f"condition={condition} query={query} classPresent={presence} business=PASS" in log
                    metric = result["primaryMetric"]
                    assert metric["scoreUnit"] == "us/op"
                    assert len(metric["rawData"]) == 1
                    assert len(metric["rawData"][0]) == receipt["measurementIterations"]
                    allocation = result["secondaryMetrics"]["gc.alloc.rate.norm"]
                    assert allocation["scoreUnit"] == "B/op"
                    collected.append({"block": block + 1, "condition": condition, "query": query,
                                      "microsecondsPerOp": metric["score"], "allocatedBytesPerOp": allocation["score"]})
                receipt["completedCells"].append(label)
                write_json(output / "run.json", receipt)
        summary = {"status": "SMOKE_ONLY_PASS" if args.smoke else "EXPLORATORY_RUN_COMPLETE", "cells": collected}
        if not args.smoke:
            comparisons = []
            for query in ("equality", "range"):
                for target in ("idle", "checked"):
                    ratios = []
                    allocation_deltas = []
                    for block in (1, 2, 3):
                        cells = {c["condition"]: c for c in collected if c["query"] == query and c["block"] == block}
                        reference = "absent" if target == "idle" else "idle"
                        ratios.append(cells[target]["microsecondsPerOp"] / cells[reference]["microsecondsPerOp"])
                        allocation_deltas.append(cells[target]["allocatedBytesPerOp"] - cells[reference]["allocatedBytesPerOp"])
                    comparisons.append({"query": query, "comparison": target + "/" + reference,
                                        "blockTimeRatios": ratios, "medianTimeRatio": statistics.median(ratios),
                                        "blockAllocatedByteDeltas": allocation_deltas})
            summary["comparisons"] = comparisons
        write_json(output / "summary.json", summary)
        receipt["status"] = summary["status"]
        receipt["resultFiles"] = {p.name: sha256(p) for p in sorted(output.glob("block-*.*"))}
        print(summary["status"], flush=True)
    except BaseException as error:
        receipt["status"] = "FAILED"
        receipt["errorType"] = type(error).__name__
        raise
    finally:
        receipt["finishedAt"] = datetime.now(timezone.utc).isoformat()
        write_json(output / "run.json", receipt)


if __name__ == "__main__":
    main()
