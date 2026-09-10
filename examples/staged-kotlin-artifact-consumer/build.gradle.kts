import groovy.json.JsonOutput
import java.io.File
import java.net.URI
import java.security.MessageDigest
import org.gradle.api.artifacts.Configuration
import org.gradle.api.artifacts.component.ModuleComponentIdentifier
import org.gradle.api.artifacts.result.UnresolvedDependencyResult
import org.gradle.api.attributes.Bundling
import org.gradle.api.attributes.Category
import org.gradle.api.attributes.LibraryElements
import org.gradle.api.attributes.Usage
import org.gradle.api.attributes.java.TargetJvmVersion

plugins {
    java
}

val routeGroup = "io.github.ym0506.routecontract"
val routeVersion = "0.2.0"
val exactRuntime = providers.gradleProperty("routecontractRuntime").get()
require(exactRuntime in listOf("5.5.2", "5.5.3")) {
    "routecontractRuntime must be exactly 5.5.2 or 5.5.3"
}
val adapter = if (exactRuntime == "5.5.2") "routecontract-shardingsphere-5.5.2" else "routecontract-shardingsphere-5.5"
val otherRuntime = if (exactRuntime == "5.5.2") "5.5.3" else "5.5.2"
val otherAdapter = if (exactRuntime == "5.5.2") "routecontract-shardingsphere-5.5" else "routecontract-shardingsphere-5.5.2"
val suppliedRepository = providers.gradleProperty("routecontractRepository").orNull
val suppliedRepositoryUrl = providers.gradleProperty("routecontractRepositoryUrl").orNull
require((suppliedRepository == null) != (suppliedRepositoryUrl == null)) {
    "Supply exactly one of routecontractRepository and routecontractRepositoryUrl"
}
val loopbackRepository = suppliedRepositoryUrl != null
val repositoryUri = if (suppliedRepositoryUrl != null) {
    val match = Regex("http://127\\.0\\.0\\.1:([1-9][0-9]{0,4})/?").matchEntire(suppliedRepositoryUrl)
    require(match != null && match.groupValues[1].toInt() <= 65535) {
        "routecontractRepositoryUrl must be canonical http://127.0.0.1:<1-65535>[/]"
    }
    URI(suppliedRepositoryUrl)
} else {
    val suppliedPath = File(requireNotNull(suppliedRepository))
    require(suppliedPath.isAbsolute) { "routecontractRepository must be an absolute staged directory" }
    val repositoryPath = suppliedPath.canonicalFile
    require(repositoryPath.isDirectory) { "routecontractRepository must be an existing staged directory" }
    repositoryPath.toURI()
}
val expectedHashes = listOf("routecontract-core", adapter).associateWith { module ->
    providers.gradleProperty("routecontractSha256.$module").get().also { value ->
        require(value.matches(Regex("[0-9a-f]{64}"))) {
            "Supply the reviewed SHA-256 for each selected first-party JAR"
        }
    }
}

repositories {
    exclusiveContent {
        forRepository {
            maven {
                name = "reviewedStaging"
                url = repositoryUri
                isAllowInsecureProtocol = loopbackRepository
                metadataSources {
                    gradleMetadata()
                    mavenPom()
                }
            }
        }
        filter { includeGroup(routeGroup) }
    }
    mavenCentral { content { excludeGroup(routeGroup) } }
}

dependencyLocking {
    lockAllConfigurations()
    lockMode = LockMode.STRICT
}

dependencies {
    testImplementation("$routeGroup:routecontract-core:$routeVersion")
    testImplementation("$routeGroup:$adapter:$routeVersion")
    testImplementation(platform("com.fasterxml.jackson:jackson-bom:2.18.9"))
    testImplementation("org.apache.shardingsphere:shardingsphere-jdbc:$exactRuntime") {
        exclude(group = "org.locationtech.jts.io", module = "jts-io-common")
    }
    testRuntimeOnly("org.apache.shardingsphere:shardingsphere-infra-url-absolutepath:$exactRuntime")
    testRuntimeOnly("org.apache.shardingsphere:shardingsphere-infra-data-source-pool-hikari:$exactRuntime")
    testRuntimeOnly("org.apache.shardingsphere:shardingsphere-standalone-mode-repository-${if (exactRuntime == "5.5.2") "jdbc" else "memory"}:$exactRuntime")
    testRuntimeOnly("org.apache.shardingsphere:shardingsphere-sharding-core:$exactRuntime")
    val parserPrefix = if (exactRuntime == "5.5.2") "" else "engine-"
    testRuntimeOnly("org.apache.shardingsphere:shardingsphere-parser-sql-${parserPrefix}sql92:$exactRuntime")
    testRuntimeOnly("org.apache.shardingsphere:shardingsphere-parser-sql-${parserPrefix}mysql:$exactRuntime")
    testRuntimeOnly("org.apache.shardingsphere:shardingsphere-authority-simple:$exactRuntime")
    testRuntimeOnly("com.mysql:mysql-connector-j:26.7.0") {
        exclude(group = "com.google.protobuf", module = "protobuf-java")
    }
    testRuntimeOnly("com.zaxxer:HikariCP:6.2.1")
    testImplementation(platform("org.junit:junit-bom:5.14.3"))
    testImplementation("org.junit.jupiter:junit-jupiter")
    testImplementation("org.testcontainers:junit-jupiter:1.21.4")
    testImplementation("org.testcontainers:mysql:1.21.4")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
    testRuntimeOnly("org.slf4j:slf4j-simple:2.0.17")
    constraints {
        testImplementation("org.apache.commons:commons-compress:1.26.0")
        if (exactRuntime == "5.5.2") {
            testImplementation("commons-logging:commons-logging:1.2") { version { strictly("1.2") } }
            // Patch the exact552 workload without introducing absent dependency modules.
            testImplementation("com.google.protobuf:protobuf-java:4.31.1") { version { strictly("4.31.1") } }
            testImplementation("org.apache.calcite:calcite-core:1.42.0") { version { strictly("1.42.0") } }
            testImplementation("org.apache.calcite:calcite-linq4j:1.42.0") { version { strictly("1.42.0") } }
            testImplementation("org.apache.calcite.avatica:avatica-core:1.28.0") { version { strictly("1.28.0") } }
            testImplementation("org.apache.calcite.avatica:avatica-metrics:1.28.0") { version { strictly("1.28.0") } }
            testImplementation("net.hydromatic:aggdesigner-algorithm:6.1") { version { strictly("6.1") } }
            testImplementation("net.minidev:json-smart:2.5.2") { version { strictly("2.5.2") } }
            testImplementation("net.minidev:accessors-smart:2.5.2") { version { strictly("2.5.2") } }
            testImplementation("org.apache.commons:commons-lang3:3.18.0") { version { strictly("3.18.0") } }
            testImplementation("org.apache.httpcomponents.core5:httpcore5:5.4.3") { version { strictly("5.4.3") } }
            testImplementation("org.apache.httpcomponents.core5:httpcore5-h2:5.4.3") { version { strictly("5.4.3") } }
            testImplementation("org.apache.httpcomponents.client5:httpclient5:5.6.3") { version { strictly("5.6.3") } }
        } else {
            testImplementation("net.hydromatic:aggdesigner-algorithm:6.1") { version { strictly("6.1") } }
            testImplementation("net.minidev:json-smart:2.4.10") { version { strictly("2.4.10") } }
            testImplementation("net.minidev:accessors-smart:2.4.9") { version { strictly("2.4.9") } }
            testImplementation("org.apache.calcite:calcite-core:1.42.0") { version { strictly("1.42.0") } }
            testImplementation("org.apache.calcite:calcite-linq4j:1.42.0") { version { strictly("1.42.0") } }
        }
    }
}

fun Configuration.enforceExactGraph() {
    resolutionStrategy.eachDependency {
        if (requested.group == "org.apache.shardingsphere" && requested.version != exactRuntime) {
            throw GradleException("RC_STAGED_RUNTIME_REJECTED: expected $exactRuntime; requested $requested")
        }
        if (requested.group == routeGroup && requested.version != routeVersion) {
            throw GradleException("RC_STAGED_LEGACY_REQUEST_REJECTED: only coordinated $routeVersion; requested $requested")
        }
    }
    resolutionStrategy.componentSelection {
        all {
            if (candidate.group == "org.apache.shardingsphere" && candidate.version != exactRuntime) {
                reject("RC_STAGED_RUNTIME_REJECTED: exact $exactRuntime required")
            }
        }
    }
}
listOf(configurations.testCompileClasspath.get(), configurations.testRuntimeClasspath.get())
    .forEach { it.enforceExactGraph() }

fun sha256(file: File): String = MessageDigest.getInstance("SHA-256")
    .digest(file.readBytes()).joinToString("") { "%02x".format(it) }

fun writeEvidence(name: String, content: String) {
    val output = layout.buildDirectory.file("routecontract-consumer-evidence/$name").get().asFile
    output.parentFile.mkdirs()
    output.writeText(content)
}

val verifySelectedGraph = tasks.register("verifySelectedGraph") {
    doLast {
        val expected = listOf("$routeGroup:routecontract-core:$routeVersion", "$routeGroup:$adapter:$routeVersion").sorted()
        val retainedArtifacts = linkedMapOf<String, List<Map<String, Any>>>()
        var runtimeComponents = emptyList<ModuleComponentIdentifier>()
        for (configuration in listOf(configurations.testCompileClasspath.get(), configurations.testRuntimeClasspath.get())) {
            val resolution = configuration.incoming.resolutionResult
            val ids = resolution.allComponents.map { it.id }
            if (ids.any { it !is ModuleComponentIdentifier && it != resolution.root.id }) {
                throw GradleException("A source/project component appeared in the independent consumer")
            }
            val components = ids.filterIsInstance<ModuleComponentIdentifier>()
            val sharding = components.filter { it.group == "org.apache.shardingsphere" }
            if (sharding.isEmpty() || sharding.any { it.version != exactRuntime }) {
                throw GradleException("RC_STAGED_RUNTIME_REJECTED: selected graph is not exact")
            }
            val selected = configuration.resolvedConfiguration.resolvedArtifacts.filter { it.moduleVersion.id.group == routeGroup }
            if (selected.map { it.moduleVersion.id.toString() }.sorted() != expected) {
                throw GradleException("Expected exactly the coordinated core and selected adapter JARs")
            }
            val scope = if (configuration.name == "testCompileClasspath") "compile" else "runtime"
            retainedArtifacts[scope] = selected.sortedBy { it.name }.map { artifact ->
                val digest = sha256(artifact.file)
                if (digest != expectedHashes[artifact.name]) {
                    throw GradleException("RC_STAGED_ARTIFACT_MISMATCH: ${artifact.name}")
                }
                mapOf("coordinate" to artifact.moduleVersion.id.toString(), "name" to artifact.file.name,
                    "sha256" to digest, "byteCount" to artifact.file.length())
            }
            if (configuration.name == "testRuntimeClasspath") {
                runtimeComponents = components
            }
        }
        writeEvidence("resolved-graph.txt", runtimeComponents.map { it.toString() }.sorted().joinToString("\n", postfix = "\n"))
        writeEvidence("resolved-first-party.json", JsonOutput.prettyPrint(JsonOutput.toJson(retainedArtifacts)) + "\n")
        val count = runtimeComponents.count { it.group == "org.apache.shardingsphere" }
        println("ROUTECONTRACT_STAGED_GRAPH_VERIFIED version=$exactRuntime artifacts=2 shardingsphereComponents=$count")
    }
}

java { toolchain { languageVersion.set(JavaLanguageVersion.of(17)) } }
tasks.withType<JavaCompile>().configureEach {
    dependsOn(verifySelectedGraph)
    options.release.set(17)
    options.encoding = "UTF-8"
    options.compilerArgs.addAll(listOf("-Xlint:all", "-Werror"))
}
tasks.test {
    dependsOn(verifySelectedGraph)
    javaLauncher.set(javaToolchains.launcherFor { languageVersion.set(JavaLanguageVersion.of(17)) })
    systemProperty("java.net.preferIPv4Stack", "true")
    providers.environmentVariable("ROUTECONTRACT_A24_PRIVATE_HOME").orNull?.let { privateHome ->
        require(File(privateHome).isAbsolute) { "ROUTECONTRACT_A24_PRIVATE_HOME must be absolute" }
        systemProperty("user.home", privateHome)
    }
    doFirst {
        require(javaLauncher.get().metadata.languageVersion.asInt() == 17) { "A24 requires a Java 17 test launcher" }
        println("ROUTECONTRACT_STAGED_TEST_LAUNCHER_CONFIGURED languageVersion=17 ipv4=true")
    }
    useJUnitPlatform()
    maxParallelForks = 1
    systemProperty("api.version", "1.44")
    systemProperty("routecontract.expectedRuntime", exactRuntime)
    systemProperty("routecontract.version", routeVersion)
    systemProperty("routecontract.coreSha256", expectedHashes.getValue("routecontract-core"))
    systemProperty("routecontract.adapterSha256", expectedHashes.getValue(adapter))
    testLogging { events("passed", "failed", "skipped"); showStandardStreams = true }
}

// Every negative can run on its own in a fresh JVM/cache. Positive locks must not
// replace the actual policy/capability conflict with a lock-state failure.
fun rejectionEvidence(configuration: Configuration, marker: String): String {
    configuration.resolutionStrategy.deactivateDependencyLocking()
    configuration.attributes {
        attribute(Usage.USAGE_ATTRIBUTE, objects.named(Usage.JAVA_RUNTIME))
        attribute(Category.CATEGORY_ATTRIBUTE, objects.named(Category.LIBRARY))
        attribute(LibraryElements.LIBRARY_ELEMENTS_ATTRIBUTE, objects.named(LibraryElements.JAR))
        attribute(Bundling.BUNDLING_ATTRIBUTE, objects.named(Bundling.EXTERNAL))
        attribute(TargetJvmVersion.TARGET_JVM_VERSION_ATTRIBUTE, 17)
    }
    val unresolved = configuration.incoming.resolutionResult.allDependencies.filterIsInstance<UnresolvedDependencyResult>()
    val failures = unresolved.map { dependency ->
        generateSequence(dependency.failure as Throwable?) { it.cause }
            .joinToString("\n") { it.message ?: it.javaClass.name }
    }
    val messages = failures.joinToString("\n")
    if (failures.isEmpty() || failures.any { !it.contains(marker) }
        || listOf("Dependency verification failed", "Could not GET ", "Could not find ").any(messages::contains)) {
        throw GradleException("Negative case did not fail solely through $marker: $messages")
    }
    if (marker == "conflict on capability") {
        val expectedConflicts = listOf(
            "conflict on capability '$routeGroup:routecontract-shardingsphere-hook-adapter:1'",
            "conflict on capability '$routeGroup:routecontract-shardingsphere-5.5:$routeVersion'")
        if (failures.any { failure -> expectedConflicts.none(failure::contains) }) {
            throw GradleException("Dual-adapter rejection did not name a reviewed adapter capability: $messages")
        }
    }
    return messages
}

fun writeRuntimeRejectionMetadata(configuration: Configuration, module: String,
                                  correctAnchors: List<String>, filename: String) {
    val wrongCoordinate = "org.apache.shardingsphere:$module:$otherRuntime"
    val matching = configuration.incoming.resolutionResult.allDependencies
        .filterIsInstance<UnresolvedDependencyResult>().filter { it.attempted.displayName == wrongCoordinate }
    require(matching.isNotEmpty()) { "Negative did not reject the actual requested selector $wrongCoordinate" }
    val failureMessages = matching.map { dependency ->
        generateSequence(dependency.failure as Throwable?) { it.cause }
            .joinToString("\n") { it.message ?: it.javaClass.name }
    }
    require(failureMessages.all { it.contains("RC_STAGED_RUNTIME_REJECTED") }) {
        "The injected wrong selector was not rejected by the whole-group policy"
    }
    val selectedAdapter = configuration.incoming.resolutionResult.allComponents
        .mapNotNull { it.id as? ModuleComponentIdentifier }
        .find { it.group == routeGroup && it.module == adapter && it.version == routeVersion }
        ?: throw GradleException("Runtime negative omitted the selected adapter")
    writeEvidence(filename, JsonOutput.prettyPrint(JsonOutput.toJson(mapOf(
        "runtime" to exactRuntime, "selectedAdapter" to selectedAdapter.toString(),
        "requestedWrongCoordinate" to wrongCoordinate, "actualUnresolvedSelector" to matching.first().attempted.displayName,
        "failureMessages" to failureMessages, "correctAnchors" to correctAnchors))) + "\n")
}

val verifyWrongAnchor = tasks.register("verifyWrongAnchor") {
    doLast {
        val wrong = dependencies.create("org.apache.shardingsphere:shardingsphere-infra-executor:$otherRuntime")
        val negative = configurations.detachedConfiguration(
            dependencies.create("$routeGroup:$adapter:$routeVersion"), wrong)
        negative.enforceExactGraph()
        val failure = rejectionEvidence(negative, "RC_STAGED_RUNTIME_REJECTED")
        writeRuntimeRejectionMetadata(negative, "shardingsphere-infra-executor", emptyList(), "wrong-anchor.json")
        writeEvidence("wrong-anchor.txt", "case=wrong-version-shardingsphere-infra-executor\n$failure\n")
        println("ROUTECONTRACT_STAGED_WRONG_ANCHOR_REJECTED version=$exactRuntime module=shardingsphere-infra-executor")
    }
}

val verifyWrongNonAnchor = tasks.register("verifyWrongNonAnchor") {
    doLast {
        val anchors = listOf("shardingsphere-infra-executor", "shardingsphere-infra-spi",
            if (exactRuntime == "5.5.2") "shardingsphere-infra-database-core" else "shardingsphere-database-connector-core")
        val requests = mutableListOf(dependencies.create("$routeGroup:$adapter:$routeVersion"))
        anchors.forEach { anchor ->
            requests.add(dependencies.create("org.apache.shardingsphere:$anchor:$exactRuntime").also {
                (it as org.gradle.api.artifacts.ModuleDependency).isTransitive = false
            })
        }
        requests.add(dependencies.create("org.apache.shardingsphere:shardingsphere-infra-common:$otherRuntime").also {
            (it as org.gradle.api.artifacts.ModuleDependency).isTransitive = false
        })
        val negative = configurations.detachedConfiguration(*requests.toTypedArray())
        negative.enforceExactGraph()
        val failure = rejectionEvidence(negative, "RC_STAGED_RUNTIME_REJECTED")
        val selected = negative.incoming.resolutionResult.allComponents.mapNotNull { it.id as? ModuleComponentIdentifier }
        if (selected.none { it.group == routeGroup && it.module == adapter && it.version == routeVersion }) {
            throw GradleException("Non-anchor negative omitted the selected adapter")
        }
        val selectedAnchors = selected.filter { it.group == "org.apache.shardingsphere" && it.module in anchors }
        if (selectedAnchors.map { it.module }.sorted() != anchors.sorted() || selectedAnchors.any { it.version != exactRuntime }) {
            throw GradleException("Non-anchor negative did not retain all three correct anchors")
        }
        writeRuntimeRejectionMetadata(negative, "shardingsphere-infra-common",
            selectedAnchors.map { it.toString() }.sorted(), "wrong-non-anchor.json")
        writeEvidence("wrong-non-anchor.txt", "case=wrong-version-shardingsphere-infra-common\n" +
            "correctAnchors=${selectedAnchors.map { it.toString() }.sorted().joinToString(",")}\n$failure\n")
        println("ROUTECONTRACT_STAGED_WRONG_NON_ANCHOR_REJECTED version=$exactRuntime module=shardingsphere-infra-common correctAnchors=3")
    }
}

fun registerDualAdapterCheck(name: String, order: List<String>, evidenceName: String) = tasks.register(name) {
    doLast {
        val negative = configurations.detachedConfiguration(*order.map {
            dependencies.create("$routeGroup:$it:$routeVersion")
        }.toTypedArray())
        val failure = rejectionEvidence(negative, "conflict on capability")
        writeEvidence(evidenceName, "case=ordinary-dual-adapter order=${order.joinToString(",")}\n$failure\n")
    }
}
val verifyDualSelectedFirst = registerDualAdapterCheck("verifyDualSelectedFirst", listOf(adapter, otherAdapter), "dual-selected-first.txt")
val verifyDualOppositeFirst = registerDualAdapterCheck("verifyDualOppositeFirst", listOf(otherAdapter, adapter), "dual-opposite-first.txt")
val verifyLegacyRequest = tasks.register("verifyLegacyRequest") {
    doLast {
        val negative = configurations.detachedConfiguration(dependencies.create("$routeGroup:routecontract-shardingsphere-5.5:0.1.2"))
        negative.enforceExactGraph()
        val failure = rejectionEvidence(negative, "RC_STAGED_LEGACY_REQUEST_REJECTED")
        writeEvidence("legacy-request.txt", "case=legacy-request\n$failure\n")
    }
}
val verifyRejectedGraphs = tasks.register("verifyRejectedGraphs") {
    dependsOn(verifyWrongAnchor, verifyWrongNonAnchor, verifyDualSelectedFirst, verifyDualOppositeFirst, verifyLegacyRequest)
    doLast {
        val names = listOf("wrong-anchor.txt", "wrong-non-anchor.txt", "dual-selected-first.txt", "dual-opposite-first.txt", "legacy-request.txt")
        writeEvidence("negative-graphs.txt", names.joinToString("\n") {
            layout.buildDirectory.file("routecontract-consumer-evidence/$it").get().asFile.readText()
        })
        println("ROUTECONTRACT_STAGED_NEGATIVES_VERIFIED version=$exactRuntime cases=5")
    }
}
tasks.check { dependsOn(verifyRejectedGraphs) }
