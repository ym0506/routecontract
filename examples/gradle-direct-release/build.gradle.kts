import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.StandardCopyOption
import java.security.MessageDigest
import java.util.HexFormat
import java.util.jar.JarFile
import org.gradle.api.artifacts.component.ModuleComponentIdentifier
import org.gradle.api.artifacts.result.ResolvedDependencyResult
import org.gradle.api.tasks.JavaExec
import org.gradle.api.tasks.compile.JavaCompile

plugins {
    application
    java
}

if (JavaVersion.current() != JavaVersion.VERSION_17) {
    throw GradleException(
        "Run this exact consumer with JDK 17; Gradle is running on ${JavaVersion.current()}"
    )
}

group = "io.github.ym0506.routecontract.examples"
version = "0.1.2"

val routeContractGroup = "io.github.ym0506.routecontract"
val routeContractModule = "routecontract-shardingsphere-5.5"
val routeContractVersion = "0.1.2"
val routeContractCoordinate = "$routeContractGroup:$routeContractModule:$routeContractVersion"
val routeContractFileName = "$routeContractModule-$routeContractVersion.jar"
val routeContractReleaseBaseUrl =
    "https://github.com/ym0506/routecontract/releases/download/v0.1.2"
val routeContractSha256 =
    "d25cd2699629890db7195e871461b25861991fe20abd776d702c690a292b72fc"
val routeContractSize = 75_891L
val ttlVersion = "2.14.2"
val jacksonVersion = "3.1.5"
val shardingSphereVersion = "5.5.3"

fun sha256(path: java.nio.file.Path): String {
    val digest = MessageDigest.getInstance("SHA-256")
    Files.newInputStream(path).use { input ->
        val buffer = ByteArray(64 * 1024)
        while (true) {
            val count = input.read(buffer)
            if (count < 0) {
                break
            }
            digest.update(buffer, 0, count)
        }
    }
    return HexFormat.of().formatHex(digest.digest())
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = "io.github.ym0506.routecontract.directrelease.DirectReleaseRuntimeProbe"
}

repositories {
    exclusiveContent {
        forRepository {
            ivy {
                name = "routeContractImmutableGitHubRelease"
                url = uri(routeContractReleaseBaseUrl)
                patternLayout {
                    artifact("[artifact]-[revision](-[classifier]).[ext]")
                }
                metadataSources {
                    artifact()
                }
            }
        }
        filter {
            includeModule(routeContractGroup, routeContractModule)
        }
    }
    mavenCentral()
}

dependencyLocking {
    lockAllConfigurations()
    lockMode.set(org.gradle.api.artifacts.dsl.LockMode.STRICT)
}

configurations.configureEach {
    resolutionStrategy {
        eachDependency {
            when {
                requested.group == routeContractGroup -> {
                    if (requested.name != routeContractModule ||
                        requested.version != routeContractVersion
                    ) {
                        throw GradleException(
                            "Only $routeContractCoordinate is allowed; requested " +
                                "${requested.group}:${requested.name}:${requested.version}"
                        )
                    }
                }
                requested.group == "com.alibaba" &&
                    requested.name == "transmittable-thread-local" -> {
                    if (requested.version != ttlVersion) {
                        throw GradleException(
                            "transmittable-thread-local must be exactly $ttlVersion"
                        )
                    }
                }
                requested.group == "tools.jackson.core" &&
                    requested.name == "jackson-core" -> {
                    if (requested.version != jacksonVersion) {
                        throw GradleException("jackson-core must be exactly $jacksonVersion")
                    }
                }
                requested.group == "org.apache.shardingsphere" -> {
                    if (requested.version != shardingSphereVersion) {
                        throw GradleException(
                            "Every Apache ShardingSphere module must be exactly " +
                                shardingSphereVersion
                        )
                    }
                }
            }
        }
    }
}

val routeContractDownload by configurations.creating {
    isCanBeConsumed = false
    isCanBeResolved = true
    isTransitive = false
}

val routeContractArtifactCollection = routeContractDownload.incoming
    .artifactView { }.artifacts

dependencies {
    routeContractDownload(routeContractCoordinate) {
        isTransitive = false
    }
}

val verifiedRouteContractJar =
    layout.buildDirectory.file("verified-routecontract/$routeContractFileName")

val verifyRouteContractArtifact = tasks.register("verifyRouteContractArtifact") {
    group = "verification"
    description = "Resolve, verify, and stage the exact immutable v0.1.2 Release JAR"
    outputs.file(verifiedRouteContractJar)
    outputs.upToDateWhen { false }
    inputs.files(routeContractArtifactCollection.artifactFiles)
        .withPropertyName("strictlyVerifiedRouteContractReleaseArtifact")
        .withPathSensitivity(PathSensitivity.NONE)

    doLast {
        val destination = verifiedRouteContractJar.get().asFile.toPath()
        val partial = destination.resolveSibling("${destination.fileName}.part")

        try {
            val artifacts = routeContractArtifactCollection.artifacts.toList()
            val edges = routeContractDownload.incoming.resolutionResult.rootComponent
                .get().dependencies.toList()
            val declared = routeContractDownload.dependencies.toList()
            if (declared.size != 1 ||
                declared.single().group != routeContractGroup ||
                declared.single().name != routeContractModule ||
                declared.single().version != routeContractVersion
            ) {
                throw GradleException(
                    "Expected one exact declared RouteContract dependency"
                )
            }
            val resolvedEdges = edges.filterIsInstance<ResolvedDependencyResult>()
            val routeContractEdges = resolvedEdges.filter { candidate ->
                val candidateRequested = candidate.requested
                    as? org.gradle.api.artifacts.component.ModuleComponentSelector
                candidateRequested?.group == routeContractGroup &&
                    candidateRequested.module == routeContractModule
            }
            val edge = routeContractEdges.singleOrNull { !it.isConstraint }
                ?: throw GradleException(
                    "Expected exactly one resolved direct RouteContract module edge"
                )
            val requested = edge.requested
                as? org.gradle.api.artifacts.component.ModuleComponentSelector
                ?: throw GradleException("RouteContract request must be a module selector")
            val selected = edge.selected.id as? ModuleComponentIdentifier
                ?: throw GradleException("RouteContract selection must be a module component")
            if (requested.group != routeContractGroup ||
                requested.module != routeContractModule ||
                requested.version != routeContractVersion ||
                selected.group != routeContractGroup ||
                selected.module != routeContractModule ||
                selected.version != routeContractVersion
            ) {
                throw GradleException(
                    "Requested and selected RouteContract modules must both be " +
                        routeContractCoordinate
                )
            }
            if (routeContractEdges.any { candidate ->
                    val candidateRequested = candidate.requested
                        as org.gradle.api.artifacts.component.ModuleComponentSelector
                    val candidateSelected = candidate.selected.id as? ModuleComponentIdentifier
                    candidateRequested.version != routeContractVersion ||
                        candidateSelected?.group != routeContractGroup ||
                        candidateSelected.module != routeContractModule ||
                        candidateSelected.version != routeContractVersion
                }
            ) {
                throw GradleException(
                    "RouteContract lock constraints must keep the exact 0.1.2 component"
                )
            }
            if (artifacts.size != 1) {
                throw GradleException(
                    "Expected exactly one non-transitive RouteContract artifact, got " +
                        artifacts.size
                )
            }
            val artifact = artifacts.single()
            val artifactComponent = artifact.id.componentIdentifier
                as? ModuleComponentIdentifier
                ?: throw GradleException(
                    "Resolved RouteContract artifact must belong to a module component"
                )
            if (artifactComponent.group != routeContractGroup ||
                artifactComponent.module != routeContractModule ||
                artifactComponent.version != routeContractVersion ||
                artifact.file.name != routeContractFileName
            ) {
                throw GradleException(
                    "Resolved RouteContract artifact identity does not match " +
                        "$routeContractCoordinate"
                )
            }

            val source = artifact.file.toPath()
            if (!Files.isRegularFile(source) || Files.isSymbolicLink(source)) {
                throw GradleException("Resolved RouteContract artifact is not a regular file")
            }
            if (Files.size(source) != routeContractSize) {
                throw GradleException(
                    "ROUTECONTRACT_ARTIFACT_SIZE_MISMATCH: expected $routeContractSize, " +
                        "got ${Files.size(source)}"
                )
            }
            val actualSha256 = sha256(source)
            if (actualSha256 != routeContractSha256) {
                throw GradleException(
                    "ROUTECONTRACT_ARTIFACT_SHA256_MISMATCH: expected " +
                        "$routeContractSha256, got $actualSha256"
                )
            }

            JarFile(source.toFile()).use { jar ->
                val moduleName = jar.manifest?.mainAttributes
                    ?.getValue("Automatic-Module-Name")
                if (moduleName != "io.github.ym0506.routecontract.shardingsphere55") {
                    throw GradleException("Unexpected RouteContract automatic module name")
                }
                val serviceDescriptor =
                    "META-INF/services/org.apache.shardingsphere.infra.executor.sql.hook." +
                        "SQLExecutionHook"
                val requiredEntries = listOf(
                    "io/github/ym0506/routecontract/RouteContract.class",
                    "io/github/ym0506/routecontract/internal/" +
                        "RouteContractSqlExecutionHook.class",
                    serviceDescriptor,
                )
                val missing = requiredEntries.filter { jar.getJarEntry(it) == null }
                if (missing.isNotEmpty()) {
                    throw GradleException("RouteContract JAR is missing entries: $missing")
                }
                val descriptor = jar.getInputStream(jar.getJarEntry(serviceDescriptor)).use {
                    String(it.readAllBytes(), StandardCharsets.UTF_8)
                }
                val expectedDescriptor =
                    "io.github.ym0506.routecontract.internal." +
                        "RouteContractSqlExecutionHook\n"
                if (descriptor != expectedDescriptor) {
                    throw GradleException("Unexpected RouteContract SPI descriptor bytes")
                }
            }

            Files.createDirectories(destination.parent)
            Files.deleteIfExists(destination)
            Files.deleteIfExists(partial)
            Files.copy(source, partial, StandardCopyOption.REPLACE_EXISTING)
            if (Files.size(partial) != routeContractSize ||
                sha256(partial) != routeContractSha256
            ) {
                throw GradleException("Staged RouteContract copy failed exact verification")
            }
            try {
                Files.move(
                    partial,
                    destination,
                    StandardCopyOption.ATOMIC_MOVE,
                    StandardCopyOption.REPLACE_EXISTING,
                )
            } catch (_: java.nio.file.AtomicMoveNotSupportedException) {
                Files.move(partial, destination, StandardCopyOption.REPLACE_EXISTING)
            }
            println("routecontractCoordinate=$routeContractCoordinate")
            println("routecontractVerifiedSize=${Files.size(destination)}")
            println("routecontractVerifiedSha256=${sha256(destination)}")
            println("ROUTECONTRACT_DIRECT_RELEASE_ARTIFACT_VERIFIED")
        } finally {
            Files.deleteIfExists(partial)
        }
    }
}

val verifiedRouteContractFiles = files(verifiedRouteContractJar)
    .builtBy(verifyRouteContractArtifact)

dependencies {
    implementation(verifiedRouteContractFiles)
    implementation(platform("com.fasterxml.jackson:jackson-bom:2.18.9"))
    implementation("com.alibaba:transmittable-thread-local") {
        version { strictly(ttlVersion) }
    }
    implementation("tools.jackson.core:jackson-core") {
        version { strictly(jacksonVersion) }
    }
    implementation("org.apache.shardingsphere:shardingsphere-infra-executor") {
        version { strictly(shardingSphereVersion) }
    }
}

val verifyRuntimeClasspath = tasks.register("verifyRuntimeClasspath") {
    group = "verification"
    description = "Verify the locked, checksummed JDK 17 / ShardingSphere 5.5.3 runtime"
    dependsOn(verifyRouteContractArtifact)
    outputs.upToDateWhen { false }
    val runtimeArtifacts = configurations.runtimeClasspath.get().incoming
        .artifactView { }.artifacts
    inputs.files(runtimeArtifacts.artifactFiles)
        .withPropertyName("strictlyVerifiedMavenRuntimeClosure")
        .withPathSensitivity(PathSensitivity.NONE)

    doLast {
        val runtime = configurations.runtimeClasspath.get()
        val components = runtime.incoming.resolutionResult.allComponents
            .mapNotNull { it.id as? ModuleComponentIdentifier }

        fun requireOne(group: String, module: String, expectedVersion: String) {
            val matches = components.filter {
                it.group == group && it.module == module
            }
            if (matches.size != 1 || matches.single().version != expectedVersion) {
                throw GradleException(
                    "Expected exactly $group:$module:$expectedVersion, got $matches"
                )
            }
        }

        requireOne("com.alibaba", "transmittable-thread-local", ttlVersion)
        requireOne("tools.jackson.core", "jackson-core", jacksonVersion)
        requireOne("com.fasterxml.jackson.core", "jackson-annotations", "2.21")
        requireOne("com.fasterxml.jackson.core", "jackson-core", "2.18.9")
        requireOne("com.fasterxml.jackson.core", "jackson-databind", "2.18.9")
        requireOne(
            "org.apache.shardingsphere",
            "shardingsphere-infra-executor",
            shardingSphereVersion,
        )
        requireOne(
            "org.apache.shardingsphere",
            "shardingsphere-infra-spi",
            shardingSphereVersion,
        )
        val wrongShardingSphere = components.filter {
            it.group == "org.apache.shardingsphere" &&
                it.version != shardingSphereVersion
        }
        if (wrongShardingSphere.isNotEmpty()) {
            throw GradleException(
                "Every resolved ShardingSphere module must be exactly " +
                    "$shardingSphereVersion: $wrongShardingSphere"
            )
        }
        val wrongFasterXmlJackson = components.filter {
            it.group == "com.fasterxml.jackson" ||
                it.group.startsWith("com.fasterxml.jackson.")
        }.filter {
            val expected = if (
                it.group == "com.fasterxml.jackson.core" &&
                it.module == "jackson-annotations"
            ) {
                "2.21"
            } else {
                "2.18.9"
            }
            it.version != expected
        }
        if (wrongFasterXmlJackson.isNotEmpty()) {
            throw GradleException(
                "Resolved FasterXML Jackson modules left the reviewed " +
                    "2.18.9 / annotations 2.21 split: " +
                    wrongFasterXmlJackson
            )
        }
        val unexpectedRouteContractMetadata = components.filter {
            it.group == routeContractGroup
        }
        if (unexpectedRouteContractMetadata.isNotEmpty()) {
            throw GradleException(
                "RouteContract must enter the runtime only through the staged verified file"
            )
        }
        val staged = verifiedRouteContractJar.get().asFile.toPath()
        if (!Files.isRegularFile(staged) || Files.isSymbolicLink(staged) ||
            Files.size(staged) != routeContractSize ||
            sha256(staged) != routeContractSha256
        ) {
            throw GradleException(
                "Staged RouteContract JAR changed before runtime classpath verification"
            )
        }
        val stagedReal = staged.toRealPath()
        val routeContractRuntimeFiles = runtime.files.filter { candidate ->
            candidate.name == routeContractFileName
        }
        if (routeContractRuntimeFiles.size != 1 ||
            routeContractRuntimeFiles.single().toPath().toRealPath() != stagedReal
        ) {
            throw GradleException(
                "Runtime classpath must contain the staged RouteContract JAR exactly once"
            )
        }
        println("routecontractRuntimeModuleCount=${components.size}")
        println("routecontractRuntimeShardingSphereVersion=$shardingSphereVersion")
        println("ROUTECONTRACT_DIRECT_RELEASE_RUNTIME_CLASSPATH_VERIFIED")
    }
}

tasks.withType<JavaCompile>().configureEach {
    dependsOn(verifyRuntimeClasspath)
    options.encoding = "UTF-8"
    options.release.set(17)
}

tasks.withType<JavaExec>().configureEach {
    dependsOn(verifyRuntimeClasspath)
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(17)
    }
    systemProperty("routecontract.expectedSha256", routeContractSha256)
    systemProperty("routecontract.expectedSize", routeContractSize.toString())
    systemProperty("routecontract.expectedVersion", routeContractVersion)
    systemProperty("routecontract.expectedTtlVersion", ttlVersion)
    systemProperty("routecontract.expectedJacksonVersion", jacksonVersion)
    systemProperty("routecontract.expectedShardingSphereVersion", shardingSphereVersion)
}

tasks.withType<Test>().configureEach {
    dependsOn(verifyRuntimeClasspath)
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.named("check") {
    dependsOn(tasks.named("run"))
}
