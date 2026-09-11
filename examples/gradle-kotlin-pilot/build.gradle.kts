import java.nio.file.Files as JFiles
import java.nio.file.LinkOption as JLinkOption
import java.nio.file.Path as JPath
import java.security.MessageDigest as JMessageDigest
import java.util.HexFormat as JHexFormat

plugins { java }

group = "io.github.ym0506.routecontract.examples"
version = "0.1.2"

repositories { mavenCentral() }

dependencies {
    testImplementation(platform("com.fasterxml.jackson:jackson-bom:2.18.9"))
    testImplementation("org.apache.shardingsphere:shardingsphere-jdbc:5.5.3") {
        exclude(group = "org.locationtech.jts.io", module = "jts-io-common")
        exclude(group = "com.google.protobuf", module = "protobuf-java")
    }
    testRuntimeOnly("org.apache.shardingsphere:shardingsphere-infra-url-absolutepath:5.5.3")
    testRuntimeOnly("org.apache.shardingsphere:shardingsphere-infra-data-source-pool-hikari:5.5.3")
    testRuntimeOnly("org.apache.shardingsphere:shardingsphere-standalone-mode-repository-memory:5.5.3")
    testRuntimeOnly("org.apache.shardingsphere:shardingsphere-sharding-core:5.5.3")
    testRuntimeOnly("org.apache.shardingsphere:shardingsphere-parser-sql-engine-sql92:5.5.3")
    testRuntimeOnly("org.apache.shardingsphere:shardingsphere-parser-sql-engine-mysql:5.5.3")
    testRuntimeOnly("org.apache.shardingsphere:shardingsphere-authority-simple:5.5.3")
    testRuntimeOnly("com.zaxxer:HikariCP:6.2.1")
    testRuntimeOnly("com.mysql:mysql-connector-j:26.7.0") {
        exclude(group = "com.google.protobuf", module = "protobuf-java")
    }

    testImplementation(platform("org.junit:junit-bom:5.14.3"))
    testImplementation("org.junit.jupiter:junit-jupiter")
    testImplementation("org.testcontainers:junit-jupiter:1.21.4")
    testImplementation("org.testcontainers:mysql:1.21.4")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
    testRuntimeOnly("org.slf4j:slf4j-simple:2.0.17")

    constraints {
        testImplementation("org.apache.calcite:calcite-core") {
            version { strictly("1.42.0") }
        }
        testImplementation("org.apache.calcite:calcite-linq4j") {
            version { strictly("1.42.0") }
        }
        testImplementation("net.minidev:json-smart") {
            version { strictly("2.4.10") }
        }
        testImplementation("net.minidev:accessors-smart") {
            version { strictly("2.4.9") }
        }
    }
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType<org.gradle.api.tasks.compile.JavaCompile>().configureEach {
    options.encoding = "UTF-8"
    options.release = 17
}

tasks.test {
    useJUnitPlatform()
    maxParallelForks = 1
    systemProperty("user.home", System.getenv("HOME"))
    systemProperty("java.io.tmpdir", System.getenv("TMPDIR"))
    systemProperty("routecontract.projectDir", projectDir.absolutePath)
    testLogging {
        events("passed", "skipped", "failed")
        exceptionFormat = org.gradle.api.tasks.testing.logging.TestExceptionFormat.FULL
        showStandardStreams = true
    }
}

// ROUTECONTRACT_KOTLIN_DSL_START
val routeContractPilotEnabled = providers.gradleProperty("routecontractPilot")
    .map { value -> value == "true" }
    .orElse(false)

if (routeContractPilotEnabled.get()) {
    val expectedRouteContractCoordinate =
        "io.github.ym0506.routecontract:routecontract-shardingsphere-5.5:0.1.2"
    val expectedRouteContractJarSha256 =
        "d25cd2699629890db7195e871461b25861991fe20abd776d702c690a292b72fc"
    val expectedRouteContractPomSha256 =
        "70b5d4161d1532e9f9cb699071790a7806d87658511d931477544fa06037b85d"
    val routeContractRepository = providers.gradleProperty("routecontractRepository")
        .orElse(providers.environmentVariable("ROUTECONTRACT_REPOSITORY"))
    if (!routeContractRepository.isPresent || routeContractRepository.get().isBlank()) {
        throw GradleException(
            "Set -ProutecontractRepository or ROUTECONTRACT_REPOSITORY for the pilot"
        )
    }

    val routeContractRepositoryInput = JPath.of(
        routeContractRepository.get()
    )
    if (!routeContractRepositoryInput.isAbsolute) {
        throw GradleException(
            "RouteContract repository must be an absolute local filesystem directory"
        )
    }
    val routeContractRepositoryNormalized = routeContractRepositoryInput.normalize()
    if (!JFiles.isDirectory(
            routeContractRepositoryNormalized,
            JLinkOption.NOFOLLOW_LINKS
        )
    ) {
        throw GradleException(
            "RouteContract repository must be a real local directory"
        )
    }
    val routeContractRepositoryRoot = routeContractRepositoryNormalized.toRealPath()
    if (routeContractRepositoryRoot != routeContractRepositoryNormalized) {
        throw GradleException(
            "RouteContract repository path must not contain symbolic-link components"
        )
    }
    val routeContractCoordinateDirectory = routeContractRepositoryRoot.resolve(
        "io/github/ym0506/routecontract/routecontract-shardingsphere-5.5/0.1.2"
    ).normalize()
    val routeContractRepositoryJar = routeContractCoordinateDirectory.resolve(
        "routecontract-shardingsphere-5.5-0.1.2.jar"
    )
    val routeContractRepositoryPom = routeContractCoordinateDirectory.resolve(
        "routecontract-shardingsphere-5.5-0.1.2.pom"
    )

    repositories {
        exclusiveContent {
            forRepository {
                maven {
                    name = "routeContractPilotRepository"
                    url = uri(routeContractRepositoryRoot.toUri())
                    metadataSources {
                        mavenPom()
                    }
                }
            }
            filter {
                includeModule(
                    "io.github.ym0506.routecontract",
                    "routecontract-shardingsphere-5.5"
                )
            }
        }
    }

    val sourceSets = the<org.gradle.api.tasks.SourceSetContainer>()
    val routeContractPilotArtifactOrigin = configurations.create(
        "routeContractPilotArtifactOrigin"
    ) {
        isCanBeConsumed = false
        isCanBeResolved = true
        isTransitive = false
    }
    val pilot = sourceSets.create("routeContractPilot") {
        compileClasspath += sourceSets.named("main").get().output +
            sourceSets.named("test").get().output
        runtimeClasspath += output + compileClasspath
    }
    configurations.named(pilot.implementationConfigurationName) {
        extendsFrom(configurations.named("testImplementation").get())
        exclude(group = "org.locationtech.jts.io", module = "jts-io-common")
        exclude(group = "com.google.protobuf", module = "protobuf-java")
    }
    configurations.named(pilot.runtimeOnlyConfigurationName) {
        extendsFrom(configurations.named("testRuntimeOnly").get())
    }

    dependencies {
        add(routeContractPilotArtifactOrigin.name, expectedRouteContractCoordinate)
        add(
            pilot.implementationConfigurationName,
            enforcedPlatform("com.fasterxml.jackson:jackson-bom:2.18.9")
        )
        add(
            pilot.implementationConfigurationName,
            platform("org.junit:junit-bom:5.14.3")
        )
        add(
            pilot.implementationConfigurationName,
            "org.junit.jupiter:junit-jupiter:5.14.3"
        )
        add(
            pilot.implementationConfigurationName,
            "org.testcontainers:junit-jupiter:1.21.4"
        )
        add(
            pilot.implementationConfigurationName,
            "org.testcontainers:mysql:1.21.4"
        )
        add(
            pilot.implementationConfigurationName,
            "org.apache.shardingsphere:shardingsphere-jdbc:5.5.3"
        ) {
            exclude(group = "org.locationtech.jts.io", module = "jts-io-common")
            exclude(group = "com.google.protobuf", module = "protobuf-java")
        }
        listOf(
            "org.apache.shardingsphere:shardingsphere-infra-url-absolutepath:5.5.3",
            "org.apache.shardingsphere:shardingsphere-infra-data-source-pool-hikari:5.5.3",
            "org.apache.shardingsphere:shardingsphere-standalone-mode-repository-memory:5.5.3",
            "org.apache.shardingsphere:shardingsphere-sharding-core:5.5.3",
            "org.apache.shardingsphere:shardingsphere-parser-sql-engine-sql92:5.5.3",
            "org.apache.shardingsphere:shardingsphere-parser-sql-engine-mysql:5.5.3",
            "org.apache.shardingsphere:shardingsphere-authority-simple:5.5.3",
        ).forEach { coordinate ->
            add(pilot.runtimeOnlyConfigurationName, coordinate)
        }
        add(pilot.runtimeOnlyConfigurationName, "com.zaxxer:HikariCP:6.2.1")
        add(pilot.runtimeOnlyConfigurationName, "com.mysql:mysql-connector-j:26.7.0") {
            exclude(group = "com.google.protobuf", module = "protobuf-java")
        }
        add(
            pilot.runtimeOnlyConfigurationName,
            "org.junit.platform:junit-platform-launcher:1.14.3"
        )
        add(pilot.runtimeOnlyConfigurationName, "org.slf4j:slf4j-simple:2.0.17")
        add(
            pilot.runtimeOnlyConfigurationName,
            "com.alibaba:transmittable-thread-local:2.14.2"
        )
        add(
            pilot.runtimeOnlyConfigurationName,
            "tools.jackson.core:jackson-core:3.1.5"
        )
        constraints {
            add(
                pilot.implementationConfigurationName,
                "org.apache.calcite:calcite-core"
            ) {
                version { strictly("1.42.0") }
            }
            add(
                pilot.implementationConfigurationName,
                "org.apache.calcite:calcite-linq4j"
            ) {
                version { strictly("1.42.0") }
            }
            add(
                pilot.implementationConfigurationName,
                "net.minidev:json-smart"
            ) {
                version { strictly("2.4.10") }
            }
            add(
                pilot.implementationConfigurationName,
                "net.minidev:accessors-smart"
            ) {
                version { strictly("2.4.9") }
            }
        }
        add(pilot.implementationConfigurationName, expectedRouteContractCoordinate)
    }

    fun exactArtifacts(
        artifacts: List<org.gradle.api.artifacts.ResolvedArtifact>,
        group: String,
        name: String,
        version: String,
        required: Boolean = true,
    ): List<org.gradle.api.artifacts.ResolvedArtifact> {
        val matches = artifacts.filter { artifact ->
            artifact.moduleVersion.id.group == group && artifact.name == name
        }
        if ((required && matches.size != 1) ||
            (!required && matches.size > 1) ||
            matches.any { artifact ->
                artifact.moduleVersion.id.version != version ||
                    artifact.extension != "jar" || artifact.classifier != null
            }
        ) {
            throw GradleException(
                "Expected ${if (required) "one" else "at most one"} unclassified " +
                    "$group:$name:$version runtime JAR"
            )
        }
        return matches
    }

    val verifyRouteContractPilotArtifactOrigin: () -> JPath = {
        val declaredDependencies = routeContractPilotArtifactOrigin.dependencies.toList()
        if (declaredDependencies.size != 1 || declaredDependencies.any { dependency ->
                dependency.group != "io.github.ym0506.routecontract" ||
                    dependency.name != "routecontract-shardingsphere-5.5" ||
                    dependency.version != "0.1.2"
            }
        ) {
            throw GradleException(
                "The artifact-origin configuration must request only " +
                    expectedRouteContractCoordinate
            )
        }
        val originArtifacts = routeContractPilotArtifactOrigin.resolvedConfiguration
            .resolvedArtifacts.toList()
        val resolvedEdges = routeContractPilotArtifactOrigin.incoming.resolutionResult
            .root.dependencies.toList()
        val resolvedEdge = resolvedEdges.singleOrNull()
            as? org.gradle.api.artifacts.result.ResolvedDependencyResult
            ?: throw GradleException(
                "The artifact-origin configuration must resolve one module edge"
            )
        val requestedModule = resolvedEdge.requested
            as? org.gradle.api.artifacts.component.ModuleComponentSelector
            ?: throw GradleException("RouteContract origin request must be a module selector")
        val selectedModule = resolvedEdge.selected.id
            as? org.gradle.api.artifacts.component.ModuleComponentIdentifier
            ?: throw GradleException("RouteContract origin selection must be a module component")
        if (requestedModule.group != "io.github.ym0506.routecontract" ||
            requestedModule.module != "routecontract-shardingsphere-5.5" ||
            requestedModule.version != "0.1.2" ||
            selectedModule.group != requestedModule.group ||
            selectedModule.module != requestedModule.module ||
            selectedModule.version != requestedModule.version
        ) {
            throw GradleException(
                "Requested and selected RouteContract origin modules must both be " +
                    expectedRouteContractCoordinate
            )
        }
        val routeContractArtifact = exactArtifacts(
            originArtifacts,
            "io.github.ym0506.routecontract",
            "routecontract-shardingsphere-5.5",
            "0.1.2"
        ).single()
        listOf(
            "JAR" to routeContractRepositoryJar,
            "POM" to routeContractRepositoryPom,
        ).forEach { expectedFile ->
            if (!expectedFile.second.startsWith(routeContractRepositoryRoot) ||
                !JFiles.isRegularFile(
                    expectedFile.second,
                    JLinkOption.NOFOLLOW_LINKS
                ) ||
                expectedFile.second.toRealPath() != expectedFile.second
            ) {
                throw GradleException(
                    "Exact RouteContract repository ${expectedFile.first} must be a real " +
                        "regular file below the repository"
                )
            }
        }
        val resolvedRouteContractJar = routeContractArtifact.file.toPath().toRealPath()
        if (resolvedRouteContractJar != routeContractRepositoryJar) {
            throw GradleException(
                "Resolved $expectedRouteContractCoordinate runtime JAR must be the exact " +
                    "coordinate file below the real local repository"
            )
        }
        listOf(
            "JAR" to Triple(
                resolvedRouteContractJar,
                expectedRouteContractJarSha256,
                "RouteContract runtime JAR SHA-256 mismatch: "
            ),
            "POM" to Triple(
                routeContractRepositoryPom,
                expectedRouteContractPomSha256,
                "RouteContract repository POM SHA-256 mismatch: "
            ),
        ).forEach { expectedFile ->
            val actualSha256 = JHexFormat.of().formatHex(
                JMessageDigest.getInstance("SHA-256").digest(
                    JFiles.readAllBytes(expectedFile.second.first)
                )
            )
            if (actualSha256 != expectedFile.second.second) {
                throw GradleException(expectedFile.second.third + actualSha256)
            }
        }
        resolvedRouteContractJar
    }

    val verifyRouteContractPilotGraph: () -> JPath = {
        val resolvedRouteContractJar = verifyRouteContractPilotArtifactOrigin()
        val runtimeConfiguration = configurations
            .getByName(pilot.runtimeClasspathConfigurationName)
        val artifacts = runtimeConfiguration.resolvedConfiguration
            .resolvedArtifacts.toList()
        val shardingSphere = artifacts.filter { artifact ->
            artifact.moduleVersion.id.group == "org.apache.shardingsphere"
        }
        if (shardingSphere.isEmpty() || shardingSphere.any { artifact ->
                artifact.moduleVersion.id.version != "5.5.3"
            }
        ) {
            throw GradleException(
                "Every resolved ShardingSphere artifact must be exactly 5.5.3"
            )
        }
        exactArtifacts(
            artifacts,
            "org.apache.shardingsphere",
            "shardingsphere-jdbc",
            "5.5.3"
        )
        exactArtifacts(artifacts, "org.apache.calcite", "calcite-core", "1.42.0")
        exactArtifacts(artifacts, "org.apache.calcite", "calcite-linq4j", "1.42.0")
        exactArtifacts(
            artifacts,
            "com.mysql",
            "mysql-connector-j",
            "26.7.0"
        )
        exactArtifacts(artifacts, "com.zaxxer", "HikariCP", "6.2.1")
        listOf(
            "org.testcontainers" to "1.21.4",
            "org.junit.jupiter" to "5.14.3",
            "org.junit.platform" to "1.14.3",
        ).forEach { expected ->
            val family = artifacts.filter { artifact ->
                artifact.moduleVersion.id.group == expected.first
            }
            if (family.isEmpty() || family.any { artifact ->
                    artifact.moduleVersion.id.version != expected.second ||
                        artifact.extension != "jar" || artifact.classifier != null
                }
            ) {
                throw GradleException(
                    "Every resolved ${expected.first} artifact must be an unclassified " +
                        "JAR exactly at ${expected.second}"
                )
            }
        }
        exactArtifacts(
            artifacts,
            "com.alibaba",
            "transmittable-thread-local",
            "2.14.2"
        )
        exactArtifacts(
            artifacts,
            "tools.jackson.core",
            "jackson-core",
            "3.1.5"
        )
        exactArtifacts(
            artifacts,
            "net.minidev",
            "json-smart",
            "2.4.10",
            required = false
        )
        exactArtifacts(
            artifacts,
            "net.minidev",
            "accessors-smart",
            "2.4.9",
            required = false
        )
        exactArtifacts(
            artifacts,
            "io.github.ym0506.routecontract",
            "routecontract-shardingsphere-5.5",
            "0.1.2"
        )
        val jackson2 = artifacts.filter { artifact ->
            val artifactGroup = artifact.moduleVersion.id.group
            artifactGroup == "com.fasterxml.jackson" ||
                artifactGroup.startsWith("com.fasterxml.jackson.")
        }
        if (jackson2.isEmpty() || jackson2.any { artifact ->
                artifact.moduleVersion.id.version != "2.18.9" ||
                    artifact.extension != "jar" || artifact.classifier != null
            }
        ) {
            throw GradleException(
                "Every resolved FasterXML Jackson artifact must be an unclassified " +
                    "JAR exactly at 2.18.9"
            )
        }
        listOf(
            "org.locationtech.jts.io" to "jts-io-common",
            "com.google.protobuf" to "protobuf-java",
        ).forEach { forbidden ->
            if (artifacts.any { artifact ->
                    artifact.moduleVersion.id.group == forbidden.first &&
                        artifact.name == forbidden.second
                }
            ) {
                throw GradleException(
                    "Forbidden runtime dependency is present: " +
                        "${forbidden.first}:${forbidden.second}"
                )
            }
        }
        resolvedRouteContractJar
    }

    val routeContractPilotArtifactProvenance = tasks.register(
        "routeContractPilotArtifactProvenance"
    ) {
        group = "verification"
        doLast {
            verifyRouteContractPilotArtifactOrigin()
            println(
                "ROUTECONTRACT_GRADLE_GAV coordinate=$expectedRouteContractCoordinate " +
                    "jarSha256=$expectedRouteContractJarSha256 " +
                    "pomSha256=$expectedRouteContractPomSha256 resolved=VERIFIED"
            )
        }
    }

    val routeContractPilotGraph = tasks.register("routeContractPilotGraph") {
        group = "verification"
        dependsOn(routeContractPilotArtifactProvenance)
        doLast {
            verifyRouteContractPilotGraph()
            println("ROUTECONTRACT_GRADLE_GRAPH VERIFIED")
        }
    }

    tasks.named<org.gradle.api.tasks.compile.JavaCompile>(pilot.compileJavaTaskName) {
        dependsOn(routeContractPilotGraph)
        javaCompiler = javaToolchains.compilerFor {
            languageVersion = JavaLanguageVersion.of(17)
        }
        options.release = 17
    }
    val routeContractCandidateFile = layout.buildDirectory
        .file("routecontract/orders.find-by-user-id.candidate.json")
    val routeContractReportFile = layout.buildDirectory
        .file(
            "test-results/routeContractPilot/" +
                "TEST-io.github.ym0506.routecontract.examples.gradle.kotlin." +
                "GradleKotlinRouteContractPilotTest.xml"
        )
    val routeContractProvenanceFile = layout.buildDirectory
        .file("routecontract/gradle-kotlin-pilot-provenance.json")
    val routeContractBuildRoot = layout.buildDirectory.get().asFile.toPath()
        .toAbsolutePath().normalize()
    val expectedRouteContractBuildRoot = projectDir.toPath().resolve("build")
        .toAbsolutePath().normalize()
    if (routeContractBuildRoot != expectedRouteContractBuildRoot) {
        throw GradleException(
            "This verified pilot lane requires the owning module's default build directory"
        )
    }
    val routeContractPilotPrepare = tasks.register("routeContractPilotPrepare") {
        group = "verification"
        doLast {
            listOf(
                routeContractCandidateFile,
                routeContractReportFile,
                routeContractProvenanceFile,
            ).forEach { fileProvider ->
                val path = fileProvider.get().asFile.toPath()
                    .toAbsolutePath().normalize()
                if (!path.startsWith(routeContractBuildRoot) || path == routeContractBuildRoot) {
                    throw GradleException(
                        "Pilot evidence path must stay below the build directory: $path"
                    )
                }
                var ancestor = path.parent
                while (ancestor != null && ancestor.startsWith(routeContractBuildRoot)) {
                    if (JFiles.isSymbolicLink(ancestor) ||
                        (JFiles.exists(
                            ancestor,
                            JLinkOption.NOFOLLOW_LINKS
                        ) && !JFiles.isDirectory(
                            ancestor,
                            JLinkOption.NOFOLLOW_LINKS
                        ))
                    ) {
                        throw GradleException(
                            "Refusing to traverse a non-directory or symlink " +
                                "pilot evidence ancestor: $ancestor"
                        )
                    }
                    if (ancestor == routeContractBuildRoot) {
                        break
                    }
                    ancestor = ancestor.parent
                }
                if (JFiles.isSymbolicLink(path) ||
                    (JFiles.exists(
                        path,
                        JLinkOption.NOFOLLOW_LINKS
                    ) && !JFiles.isRegularFile(
                        path,
                        JLinkOption.NOFOLLOW_LINKS
                    ))
                ) {
                    throw GradleException(
                        "Refusing to replace a non-regular pilot evidence path: $path"
                    )
                }
                JFiles.deleteIfExists(path)
            }
        }
    }
    tasks.register<org.gradle.api.tasks.testing.Test>("routeContractPilot") {
        group = "verification"
        dependsOn(routeContractPilotPrepare, routeContractPilotGraph)
        testClassesDirs = pilot.output.classesDirs
        classpath = pilot.runtimeClasspath
        javaLauncher = javaToolchains.launcherFor {
            languageVersion = JavaLanguageVersion.of(17)
        }
        useJUnitPlatform()
        maxParallelForks = 1
        systemProperty("user.home", System.getenv("HOME"))
        systemProperty("java.io.tmpdir", System.getenv("TMPDIR"))
        systemProperty("routecontract.projectDir", projectDir.absolutePath)
        systemProperty("routecontract.candidateRoot", "build/routecontract")
        systemProperty(
            "routecontract.provenancePath",
            "build/routecontract/gradle-kotlin-pilot-provenance.json"
        )
        systemProperty("routecontract.coordinate", expectedRouteContractCoordinate)
        systemProperty(
            "routecontract.repositoryRoot",
            routeContractRepositoryRoot.toString()
        )
        systemProperty(
            "routecontract.artifactPomPath",
            routeContractRepositoryPom.toString()
        )
        systemProperty(
            "routecontract.artifactJarSha256",
            expectedRouteContractJarSha256
        )
        systemProperty(
            "routecontract.artifactPomSha256",
            expectedRouteContractPomSha256
        )
        systemProperty(
            "routecontract.artifactJarName",
            "routecontract-shardingsphere-5.5-0.1.2.jar"
        )
        doFirst {
            val artifactPath = verifyRouteContractPilotGraph()
            systemProperty(
                "routecontract.artifactJarPath",
                artifactPath.toRealPath().toString()
            )
        }
        testLogging {
            events("passed", "skipped", "failed")
            exceptionFormat = org.gradle.api.tasks.testing.logging.TestExceptionFormat.FULL
            showStandardStreams = true
        }
    }
}
// ROUTECONTRACT_KOTLIN_DSL_END
