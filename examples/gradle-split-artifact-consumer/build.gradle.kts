import org.gradle.api.artifacts.Configuration
import org.gradle.api.artifacts.ExternalModuleDependency
import org.gradle.api.artifacts.component.ModuleComponentIdentifier
import org.gradle.api.artifacts.result.UnresolvedDependencyResult
import org.gradle.api.attributes.Bundling
import org.gradle.api.attributes.Category
import org.gradle.api.attributes.LibraryElements
import org.gradle.api.attributes.Usage
import org.gradle.api.attributes.java.TargetJvmVersion
import org.gradle.api.tasks.JavaExec
import org.gradle.api.tasks.compile.JavaCompile

plugins {
    application
    java
}

group = "io.github.ym0506.routecontract.examples"
version = "0.2.0"

val routeContractGroup = "io.github.ym0506.routecontract"
val routeContractVersion = "0.2.0"
val coreModule = "routecontract-core"
val adapter552Module = "routecontract-shardingsphere-5.5.2"
val adapter553Module = "routecontract-shardingsphere-5.5"
val adapterCapability =
    "$routeContractGroup:routecontract-shardingsphere-hook-adapter:1"
val coreOwnerCapability = "$routeContractGroup:routecontract-core-owner:1"
val shardingSphereGroup = "org.apache.shardingsphere"
val requestRejectionMarker = "RC_GRADLE_SHARDINGSPHERE_REQUEST_VERSION_REJECTED"
val selectionRejectionMarker = "RC_GRADLE_SHARDINGSPHERE_SELECTED_VERSION_REJECTED"

val requestedAdapterVersion = providers.gradleProperty("routecontractAdapterVersion")
if (!requestedAdapterVersion.isPresent || requestedAdapterVersion.get().isBlank()) {
    throw GradleException(
        "Set routecontractAdapterVersion to exactly 5.5.2 or 5.5.3"
    )
}
val adapterVersion = requestedAdapterVersion.get()
val adapterModule = when (adapterVersion) {
    "5.5.2" -> adapter552Module
    "5.5.3" -> adapter553Module
    else -> throw GradleException(
        "routecontractAdapterVersion must be exactly 5.5.2 or 5.5.3"
    )
}
val otherShardingSphereVersion = if (adapterVersion == "5.5.2") "5.5.3" else "5.5.2"

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = "io.github.ym0506.routecontract.examples.split.SplitArtifactConsumerProbe"
}

fun ExternalModuleDependency.requireExactRouteContractVersion() {
    version {
        strictly(routeContractVersion)
    }
}

fun ExternalModuleDependency.requireCoreOwner() {
    requireExactRouteContractVersion()
    capabilities {
        requireCapability(coreOwnerCapability)
    }
}

fun ExternalModuleDependency.requireAdapterSlot() {
    requireExactRouteContractVersion()
    capabilities {
        requireCapability(adapterCapability)
    }
}

dependencies {
    implementation("$routeContractGroup:$coreModule:$routeContractVersion") {
        requireCoreOwner()
    }
    implementation("$routeContractGroup:$adapterModule:$routeContractVersion") {
        requireAdapterSlot()
    }
}

fun Configuration.useJava17RuntimeAttributes() {
    attributes {
        attribute(Category.CATEGORY_ATTRIBUTE, objects.named(Category.LIBRARY))
        attribute(Usage.USAGE_ATTRIBUTE, objects.named(Usage.JAVA_RUNTIME))
        attribute(LibraryElements.LIBRARY_ELEMENTS_ATTRIBUTE, objects.named(LibraryElements.JAR))
        attribute(Bundling.BUNDLING_ATTRIBUTE, objects.named(Bundling.EXTERNAL))
        attribute(TargetJvmVersion.TARGET_JVM_VERSION_ATTRIBUTE, 17)
    }
}

val wrongNonAnchorRuntime = configurations.create("wrongNonAnchorRuntime") {
    isCanBeConsumed = false
    isCanBeResolved = true
    extendsFrom(configurations.implementation.get())
    useJava17RuntimeAttributes()
}

val dualAdapter552First = configurations.create("dualAdapter552First") {
    isCanBeConsumed = false
    isCanBeResolved = true
    useJava17RuntimeAttributes()
}

val dualAdapter553First = configurations.create("dualAdapter553First") {
    isCanBeConsumed = false
    isCanBeResolved = true
    useJava17RuntimeAttributes()
}

dependencies {
    add(
        wrongNonAnchorRuntime.name,
        "$shardingSphereGroup:shardingsphere-infra-common:$otherShardingSphereVersion",
    )

    add(dualAdapter552First.name, "$routeContractGroup:$adapter552Module:$routeContractVersion") {
        requireAdapterSlot()
    }
    add(dualAdapter552First.name, "$routeContractGroup:$adapter553Module:$routeContractVersion") {
        requireAdapterSlot()
    }

    add(dualAdapter553First.name, "$routeContractGroup:$adapter553Module:$routeContractVersion") {
        requireAdapterSlot()
    }
    add(dualAdapter553First.name, "$routeContractGroup:$adapter552Module:$routeContractVersion") {
        requireAdapterSlot()
    }
}

fun Configuration.enforceExactShardingSphereVersion() {
    resolutionStrategy.eachDependency {
        if (requested.group == shardingSphereGroup && requested.version != adapterVersion) {
            throw GradleException(
                "$requestRejectionMarker: expected $adapterVersion; requested " +
                    "${requested.group}:${requested.name}:${requested.version}"
            )
        }
    }
    resolutionStrategy.componentSelection {
        all {
            if (candidate.group == shardingSphereGroup && candidate.version != adapterVersion) {
                reject(
                    "$selectionRejectionMarker: expected $adapterVersion; candidate " +
                        "${candidate.group}:${candidate.module}:${candidate.version}"
                )
            }
        }
    }
}

listOf(
    configurations.compileClasspath.get(),
    configurations.runtimeClasspath.get(),
    wrongNonAnchorRuntime,
).forEach { target ->
    target.enforceExactShardingSphereVersion()
}

fun failureChain(failure: Throwable): String = generateSequence(failure) { it.cause }
    .joinToString("\n") { current ->
        "${current.javaClass.name}: ${current.message.orEmpty()}"
    }

fun requireResolutionFailure(
    target: Configuration,
    requiredTexts: List<String>,
    label: String,
) : String {
    val unresolved = target.incoming.resolutionResult.allDependencies
        .filterIsInstance<UnresolvedDependencyResult>()
        .toList()
    if (unresolved.isEmpty()) {
        throw GradleException("$label unexpectedly resolved")
    }
    val messages = unresolved.joinToString("\n") { dependency ->
        "requested=${dependency.requested.displayName}\n" +
            failureChain(dependency.failure)
    }
    val missing = requiredTexts.filterNot(messages::contains)
    if (missing.isNotEmpty()) {
        throw GradleException(
            "$label failed for an unexpected reason; missing $missing in:\n$messages",
        )
    }
    return messages
}

val verifySelectedGraph = tasks.register("verifySelectedGraph") {
    group = "verification"
    description = "Require core 0.2.0, one exact adapter, and one ShardingSphere version"

    doLast {
        val runtime = configurations.runtimeClasspath.get()
        val artifacts = runtime.resolvedConfiguration.resolvedArtifacts.toList()
        val routeContractArtifacts = artifacts.filter { artifact ->
            artifact.moduleVersion.id.group == routeContractGroup
        }
        val routeContractCoordinates = routeContractArtifacts.map { artifact ->
            val id = artifact.moduleVersion.id
            "${id.group}:${artifact.name}:${id.version}"
        }.sorted()
        val expectedRouteContractCoordinates = listOf(
            "$routeContractGroup:$adapterModule:$routeContractVersion",
            "$routeContractGroup:$coreModule:$routeContractVersion",
        ).sorted()
        if (routeContractCoordinates != expectedRouteContractCoordinates) {
            throw GradleException(
                "Expected only core plus one exact adapter; got $routeContractCoordinates"
            )
        }

        val selectedShardingSphere = runtime.incoming.resolutionResult.allComponents
            .mapNotNull { component -> component.id as? ModuleComponentIdentifier }
            .filter { component -> component.group == shardingSphereGroup }
        if (selectedShardingSphere.isEmpty()) {
            throw GradleException("Expected a resolved ShardingSphere runtime closure")
        }
        val wrongSelected = selectedShardingSphere.filter { component ->
            component.version != adapterVersion
        }
        if (wrongSelected.isNotEmpty()) {
            throw GradleException(
                "$selectionRejectionMarker: expected $adapterVersion; selected $wrongSelected"
            )
        }
        println(
            "ROUTECONTRACT_GRADLE_SPLIT_GRAPH_VERIFIED " +
                "adapter=$adapterModule routeContractVersion=$routeContractVersion " +
                "shardingSphereVersion=$adapterVersion " +
                "shardingSphereComponents=${selectedShardingSphere.size}"
        )
    }
}

val verifyWrongNonAnchorRejected = tasks.register("verifyWrongNonAnchorRejected") {
    group = "verification"
    description = "Prove a wrong-version non-anchor ShardingSphere request fails resolution"
    doLast {
        requireResolutionFailure(
            wrongNonAnchorRuntime,
            listOf(requestRejectionMarker),
            "wrong-version non-anchor graph",
        )
        println(
            "ROUTECONTRACT_GRADLE_WRONG_NON_ANCHOR_REJECTED " +
                "module=shardingsphere-infra-common requested=$otherShardingSphereVersion " +
                "expected=$adapterVersion"
        )
    }
}

fun registerDualAdapterCheck(
    taskName: String,
    target: Configuration,
    declarationOrder: String,
) = tasks.register(taskName) {
    group = "verification"
    description = "Prove the shared adapter capability rejects $declarationOrder"
    doLast {
        val messages = requireResolutionFailure(
            target,
            listOf("Cannot select module with conflict on capability"),
            "dual-adapter graph ($declarationOrder)",
        )
        val sharedCapabilityName = "routecontract-shardingsphere-hook-adapter"
        val legacyCapabilityName = "routecontract-shardingsphere-5.5"
        if (!messages.contains(sharedCapabilityName) &&
            !messages.contains(legacyCapabilityName)
        ) {
            throw GradleException(
                "dual-adapter graph did not name a reviewed adapter capability"
            )
        }
        println(
            "ROUTECONTRACT_GRADLE_DUAL_ADAPTER_REJECTED " +
                "order=$declarationOrder capability=$adapterCapability"
        )
    }
}

val verifyDualAdapter552First = registerDualAdapterCheck(
    "verifyDualAdapter552First",
    dualAdapter552First,
    "5.5.2-then-5.5.3",
)
val verifyDualAdapter553First = registerDualAdapterCheck(
    "verifyDualAdapter553First",
    dualAdapter553First,
    "5.5.3-then-5.5.2",
)

tasks.withType<JavaCompile>().configureEach {
    dependsOn(verifySelectedGraph)
    options.encoding = "UTF-8"
    options.release.set(17)
}

tasks.withType<JavaExec>().configureEach {
    dependsOn(verifySelectedGraph)
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(17)
    }
    systemProperty("routecontract.expectedShardingSphereVersion", adapterVersion)
}

tasks.named("check") {
    dependsOn(tasks.named("run"))
    dependsOn(verifyWrongNonAnchorRejected)
    dependsOn(verifyDualAdapter552First)
    dependsOn(verifyDualAdapter553First)
}
