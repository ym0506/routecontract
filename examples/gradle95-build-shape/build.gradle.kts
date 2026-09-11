import java.nio.file.Files as JFiles
import java.nio.file.LinkOption as JLinkOption
import java.nio.file.Path as JPath
import java.security.MessageDigest as JMessageDigest
import java.util.HexFormat as JHexFormat

plugins { java }

group = "io.github.ym0506.routecontract.examples"
version = "0.1.2"

val supportedBootBoms = setOf("3.5.16", "4.1.0")
val bootBomProperty = providers.gradleProperty("routecontractBootBom")
if (!bootBomProperty.isPresent || bootBomProperty.get().isBlank()) {
    throw GradleException("Set routecontractBootBom to exactly 3.5.16 or 4.1.0")
}
val bootBomVersion = bootBomProperty.get()
if (bootBomVersion !in supportedBootBoms) {
    throw GradleException(
        "routecontractBootBom must be exactly 3.5.16 or 4.1.0"
    )
}

val pilotProperty = providers.gradleProperty("routecontractPilot")
val pilotPropertyValue = if (pilotProperty.isPresent) pilotProperty.get() else null
if (pilotPropertyValue != null && pilotPropertyValue !in setOf("true", "false")) {
    throw GradleException("routecontractPilot must be exactly true or false")
}
val pilotEnabled = pilotPropertyValue == "true"
val repositoryProperty = providers.gradleProperty("routecontractRepository")
if (!pilotEnabled && repositoryProperty.isPresent) {
    throw GradleException(
        "routecontractRepository is accepted only when routecontractPilot=true"
    )
}

repositories { mavenCentral() }

dependencies {
    testImplementation(platform("org.springframework.boot:spring-boot-dependencies:$bootBomVersion"))
    testImplementation("org.junit.jupiter:junit-jupiter")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
    testRuntimeOnly("com.zaxxer:HikariCP")
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType<org.gradle.api.tasks.compile.JavaCompile>().configureEach {
    options.encoding = "UTF-8"
    options.release = 17
}

tasks.test {
    useJUnitPlatform()
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(21)
    }
    systemProperty("routecontract.expectedBootBom", bootBomVersion)
    maxParallelForks = 1
}

fun sha256(bytes: ByteArray): String = JHexFormat.of().formatHex(
    JMessageDigest.getInstance("SHA-256").digest(bytes)
)

fun classMajorVersion(path: JPath): Int {
    if (!JFiles.isRegularFile(path, JLinkOption.NOFOLLOW_LINKS)) {
        throw GradleException("Expected a regular compiled class file: $path")
    }
    val bytes = JFiles.readAllBytes(path)
    if (bytes.size < 8 || bytes[0].toInt() != -54 || bytes[1].toInt() != -2 ||
        bytes[2].toInt() != -70 || bytes[3].toInt() != -66
    ) {
        throw GradleException("Compiled output has no exact JVM class header: $path")
    }
    return (bytes[6].toInt() and 0xff) * 256 + (bytes[7].toInt() and 0xff)
}

fun artifactCoordinates(
    configuration: org.gradle.api.artifacts.Configuration,
): List<String> = configuration.resolvedConfiguration.resolvedArtifacts
    .map { artifact ->
        val id = artifact.moduleVersion.id
        "${id.group}:${artifact.name}:${id.version}:" +
            "${artifact.classifier ?: ""}:${artifact.extension}"
    }
    .sorted()

fun exactArtifact(
    artifacts: List<org.gradle.api.artifacts.ResolvedArtifact>,
    group: String,
    name: String,
    version: String,
): org.gradle.api.artifacts.ResolvedArtifact {
    val matches = artifacts.filter { artifact ->
        artifact.moduleVersion.id.group == group && artifact.name == name
    }
    if (matches.size != 1 || matches.single().moduleVersion.id.version != version ||
        matches.single().classifier != null || matches.single().extension != "jar"
    ) {
        throw GradleException("Expected exactly one unclassified $group:$name:$version JAR")
    }
    return matches.single()
}

fun canonicalComponentId(
    identifier: org.gradle.api.artifacts.component.ComponentIdentifier,
): String = when (identifier) {
    is org.gradle.api.artifacts.component.ModuleComponentIdentifier ->
        "module:${identifier.group}:${identifier.module}:${identifier.version}"
    is org.gradle.api.artifacts.component.ProjectComponentIdentifier ->
        "project:${identifier.build.buildPath}:${identifier.projectPath}"
    else -> throw GradleException(
        "Unsupported component identifier in the exact target graph: " +
            identifier.javaClass.name
    )
}

fun canonicalRequestedId(
    selector: org.gradle.api.artifacts.component.ComponentSelector,
): String = when (selector) {
    is org.gradle.api.artifacts.component.ModuleComponentSelector ->
        "module:${selector.group}:${selector.module}:${selector.version}"
    is org.gradle.api.artifacts.component.ProjectComponentSelector ->
        "project:${selector.buildPath}:${selector.projectPath}"
    else -> throw GradleException(
        "Unsupported component selector in the exact target graph: " +
            selector.javaClass.name
    )
}

data class CanonicalResolutionGraph(
    val sha256: String,
    val componentCount: Int,
    val edgeCount: Int,
)

fun canonicalResolutionGraph(
    configuration: org.gradle.api.artifacts.Configuration,
): CanonicalResolutionGraph {
    val result = configuration.incoming.resolutionResult
    val failures = result.allDependencies
        .filterIsInstance<org.gradle.api.artifacts.result.UnresolvedDependencyResult>()
        .toList()
    if (failures.isNotEmpty()) {
        throw GradleException(
            "Target ResolutionResult must have no unresolved dependency edges"
        )
    }
    val components = result.allComponents.map { component ->
        "component|${canonicalComponentId(component.id)}"
    }.sorted()
    if (components.size != components.toSet().size) {
        throw GradleException("Target ResolutionResult contains duplicate component IDs")
    }
    val edges = result.allComponents.flatMap { component ->
        val from = canonicalComponentId(component.id)
        component.dependencies.map { dependency ->
            val resolved = dependency
                as? org.gradle.api.artifacts.result.ResolvedDependencyResult
                ?: throw GradleException(
                    "Target ResolutionResult contains a non-resolved dependency edge"
                )
            "edge|from=$from|requested=${canonicalRequestedId(resolved.requested)}|" +
                "selected=${canonicalComponentId(resolved.selected.id)}|" +
                "constraint=${resolved.isConstraint}"
        }
    }.sorted()
    val lines = components + edges
    val fingerprint = sha256((lines.joinToString("\n") + "\n").toByteArray())
    return CanonicalResolutionGraph(
        sha256 = fingerprint,
        componentCount = components.size,
        edgeCount = edges.size,
    )
}

val expectedTargetVersions = mapOf(
    "3.5.16" to ("6.3.3" to "5.12.2"),
    "4.1.0" to ("7.0.2" to "6.0.3"),
)

tasks.register("routeContractBuildShapeTargetGraph") {
    group = "verification"
    doLast {
        val targetRuntime = configurations.testRuntimeClasspath.get()
        val bootBomEdges = targetRuntime.incoming.resolutionResult.root.dependencies
            .filterIsInstance<org.gradle.api.artifacts.result.ResolvedDependencyResult>()
            .filter { edge ->
                val requested = edge.requested
                requested is org.gradle.api.artifacts.component.ModuleComponentSelector &&
                    requested.group == "org.springframework.boot" &&
                    requested.module == "spring-boot-dependencies"
            }
        val bootBomEdge = bootBomEdges.singleOrNull()
            ?: throw GradleException("Expected exactly one direct Spring Boot BOM edge")
        val requestedBootBom = bootBomEdge.requested
            as org.gradle.api.artifacts.component.ModuleComponentSelector
        val selectedBootBom = bootBomEdge.selected.id
            as? org.gradle.api.artifacts.component.ModuleComponentIdentifier
            ?: throw GradleException("Spring Boot BOM must select a module component")
        if (requestedBootBom.version != bootBomVersion ||
            selectedBootBom.group != "org.springframework.boot" ||
            selectedBootBom.module != "spring-boot-dependencies" ||
            selectedBootBom.version != bootBomVersion
        ) {
            throw GradleException(
                "Requested and selected Spring Boot BOM must both be exactly $bootBomVersion"
            )
        }
        targetRuntime.resolvedConfiguration.rethrowFailure()
        val artifacts = targetRuntime.resolvedConfiguration.resolvedArtifacts.toList()
        if (artifacts.any { artifact ->
                artifact.moduleVersion.id.group == "io.github.ym0506.routecontract"
            }
        ) {
            throw GradleException(
                "RouteContract must be absent from the target test runtime graph"
            )
        }
        val expected = expectedTargetVersions.getValue(bootBomVersion)
        exactArtifact(artifacts, "com.zaxxer", "HikariCP", expected.first)
        exactArtifact(
            artifacts,
            "org.junit.jupiter",
            "junit-jupiter-api",
            expected.second,
        )
        val graph = canonicalResolutionGraph(targetRuntime)
        println(
            "ROUTECONTRACT_BUILD_SHAPE_TARGET_GRAPH " +
                "bootBom=$bootBomVersion sha256=${graph.sha256} " +
                "components=${graph.componentCount} edges=${graph.edgeCount} " +
                "bomEdge=DIRECT_EXACT routeContract=ABSENT " +
                "hikari=${expected.first} junit=${expected.second}"
        )
    }
}

if (pilotEnabled) {
    val expectedCoordinate =
        "io.github.ym0506.routecontract:routecontract-shardingsphere-5.5:0.1.2"
    val expectedJarSha256 =
        "d25cd2699629890db7195e871461b25861991fe20abd776d702c690a292b72fc"
    val expectedPomSha256 =
        "70b5d4161d1532e9f9cb699071790a7806d87658511d931477544fa06037b85d"
    if (!repositoryProperty.isPresent || repositoryProperty.get().isBlank()) {
        throw GradleException(
            "Set the absolute routecontractRepository when routecontractPilot=true"
        )
    }
    val repositoryInput = JPath.of(repositoryProperty.get())
    if (!repositoryInput.isAbsolute) {
        throw GradleException("routecontractRepository must be an absolute local directory")
    }
    val repositoryNormalized = repositoryInput.normalize()
    if (!JFiles.isDirectory(repositoryNormalized, JLinkOption.NOFOLLOW_LINKS)) {
        throw GradleException("routecontractRepository must be a real local directory")
    }
    val repositoryRoot = repositoryNormalized.toRealPath()
    if (repositoryRoot != repositoryNormalized) {
        throw GradleException(
            "routecontractRepository path must not contain symbolic-link components"
        )
    }
    val coordinateDirectory = repositoryRoot.resolve(
        "io/github/ym0506/routecontract/routecontract-shardingsphere-5.5/0.1.2"
    )
    val expectedJar = coordinateDirectory.resolve(
        "routecontract-shardingsphere-5.5-0.1.2.jar"
    )
    val expectedPom = coordinateDirectory.resolve(
        "routecontract-shardingsphere-5.5-0.1.2.pom"
    )

    repositories {
        exclusiveContent {
            forRepository {
                maven {
                    name = "routeContractBuildShapeRepository"
                    url = uri(repositoryRoot.toUri())
                    metadataSources { mavenPom() }
                }
            }
            filter {
                includeModule(
                    "io.github.ym0506.routecontract",
                    "routecontract-shardingsphere-5.5",
                )
            }
        }
    }

    val sourceSets = the<org.gradle.api.tasks.SourceSetContainer>()
    val pilot = sourceSets.create("routeContractPilot") {
        compileClasspath += sourceSets.named("main").get().output
        runtimeClasspath += output + compileClasspath
    }
    val origin = configurations.create("routeContractBuildShapeArtifactOrigin") {
        isCanBeConsumed = false
        isCanBeResolved = true
        isTransitive = false
    }
    dependencies {
        add(origin.name, expectedCoordinate)
        add(pilot.implementationConfigurationName, expectedCoordinate) {
            isTransitive = false
        }
        add(
            pilot.implementationConfigurationName,
            "org.junit.jupiter:junit-jupiter:5.14.3",
        )
        add(
            pilot.runtimeOnlyConfigurationName,
            "org.junit.platform:junit-platform-launcher:1.14.3",
        )
    }

    fun verifyOrigin(): JPath {
        listOf("JAR" to expectedJar, "POM" to expectedPom).forEach { expectedFile ->
            if (!expectedFile.second.startsWith(repositoryRoot) ||
                !JFiles.isRegularFile(expectedFile.second, JLinkOption.NOFOLLOW_LINKS) ||
                expectedFile.second.toRealPath() != expectedFile.second
            ) {
                throw GradleException(
                    "Exact RouteContract ${expectedFile.first} must be a real coordinate file"
                )
            }
        }
        val artifacts = origin.resolvedConfiguration.resolvedArtifacts.toList()
        val resolved = exactArtifact(
            artifacts,
            "io.github.ym0506.routecontract",
            "routecontract-shardingsphere-5.5",
            "0.1.2",
        ).file.toPath().toRealPath()
        if (resolved != expectedJar) {
            throw GradleException(
                "Resolved RouteContract JAR must be the exact local-repository coordinate file"
            )
        }
        val actualJarSha256 = sha256(JFiles.readAllBytes(resolved))
        val actualPomSha256 = sha256(JFiles.readAllBytes(expectedPom))
        if (actualJarSha256 != expectedJarSha256) {
            throw GradleException("RouteContract runtime JAR SHA-256 mismatch: $actualJarSha256")
        }
        if (actualPomSha256 != expectedPomSha256) {
            throw GradleException("RouteContract repository POM SHA-256 mismatch: $actualPomSha256")
        }
        return resolved
    }

    val pilotGraph = tasks.register("routeContractBuildShapePilotGraph") {
        group = "verification"
        doLast {
            verifyOrigin()
            val runtimeConfiguration = configurations.getByName(
                pilot.runtimeClasspathConfigurationName
            )
            val artifacts = runtimeConfiguration.resolvedConfiguration
                .resolvedArtifacts.toList()
            exactArtifact(
                artifacts,
                "io.github.ym0506.routecontract",
                "routecontract-shardingsphere-5.5",
                "0.1.2",
            )
            exactArtifact(
                artifacts,
                "org.junit.jupiter",
                "junit-jupiter-api",
                "5.14.3",
            )
            val coordinates = artifactCoordinates(runtimeConfiguration)
            val fingerprint = sha256((coordinates.joinToString("\n") + "\n").toByteArray())
            println(
                "ROUTECONTRACT_BUILD_SHAPE_PILOT_GRAPH " +
                    "sha256=$fingerprint coordinate=$expectedCoordinate " +
                    "jarSha256=$expectedJarSha256 pomSha256=$expectedPomSha256"
            )
        }
    }

    tasks.named<org.gradle.api.tasks.compile.JavaCompile>(pilot.compileJavaTaskName) {
        dependsOn(pilotGraph)
        javaCompiler = javaToolchains.compilerFor {
            languageVersion = JavaLanguageVersion.of(17)
        }
        options.release = 17
    }

    val toolchains = tasks.register("routeContractBuildShapeToolchains") {
        group = "verification"
        doLast {
            if (JavaVersion.current() != JavaVersion.VERSION_21) {
                throw GradleException("Gradle must run on JDK 21")
            }
            val mainVersion = javaToolchains.compilerFor {
                languageVersion = JavaLanguageVersion.of(21)
            }.get().metadata.languageVersion.asInt()
            val pilotCompilerVersion = javaToolchains.compilerFor {
                languageVersion = JavaLanguageVersion.of(17)
            }.get().metadata.languageVersion.asInt()
            val pilotLauncherVersion = javaToolchains.launcherFor {
                languageVersion = JavaLanguageVersion.of(17)
            }.get().metadata.languageVersion.asInt()
            if (mainVersion != 21 || pilotCompilerVersion != 17 ||
                pilotLauncherVersion != 17
            ) {
                throw GradleException("Unexpected build-shape toolchain selection")
            }
            println(
                "ROUTECONTRACT_BUILD_SHAPE_TOOLCHAINS " +
                    "gradleRuntime=21 mainCompiler=21 mainRelease=17 " +
                    "pilotCompiler=17 pilotRelease=17 pilotTestLauncher=17"
            )
        }
    }

    val bytecode = tasks.register("routeContractBuildShapeBytecode") {
        group = "verification"
        dependsOn(tasks.named("classes"), tasks.named(pilot.classesTaskName))
        doLast {
            val mainClass = layout.buildDirectory.file(
                "classes/java/main/io/github/ym0506/routecontract/examples/" +
                    "buildshape/BuildShapeApplication.class"
            ).get().asFile.toPath()
            val pilotClass = layout.buildDirectory.file(
                "classes/java/routeContractPilot/io/github/ym0506/" +
                    "routecontract/examples/buildshape/" +
                    "RouteContractBuildShapePilotTest.class"
            ).get().asFile.toPath()
            val mainMajor = classMajorVersion(mainClass)
            val pilotMajor = classMajorVersion(pilotClass)
            if (mainMajor != 61 || pilotMajor != 61) {
                throw GradleException(
                    "Main and pilot compiled class headers must both be Java 17 major 61"
                )
            }
            println(
                "ROUTECONTRACT_BUILD_SHAPE_BYTECODE " +
                    "mainClassMajor=$mainMajor pilotClassMajor=$pilotMajor"
            )
        }
    }

    tasks.register<org.gradle.api.tasks.testing.Test>("routeContractBuildShapePilot") {
        group = "verification"
        description = "Runs the isolated RouteContract build-shape compatibility check."
        dependsOn(pilotGraph, toolchains, bytecode)
        testClassesDirs = pilot.output.classesDirs
        classpath = pilot.runtimeClasspath
        useJUnitPlatform()
        javaLauncher = javaToolchains.launcherFor {
            languageVersion = JavaLanguageVersion.of(17)
        }
        maxParallelForks = 1
        outputs.upToDateWhen { false }
        doFirst {
            val resolvedJar = verifyOrigin()
            systemProperty("routecontract.expectedArtifactJar", resolvedJar.toString())
            systemProperty("routecontract.expectedJarSha256", expectedJarSha256)
            systemProperty("routecontract.expectedPomSha256", expectedPomSha256)
            systemProperty("routecontract.expectedRepository", repositoryRoot.toString())
        }
    }
}
