import org.gradle.api.initialization.resolve.RepositoriesMode

pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        mavenCentral()
    }
}

rootProject.name = "routecontract-gradle-split-artifact-consumer"

// This is a local 0.2 development fixture. Composite substitution preserves the
// projects' published variants, including their mutually exclusive capabilities,
// without publishing snapshots to Maven Local or touching a Central staging tree.
includeBuild("../..") {
    dependencySubstitution {
        substitute(module("io.github.ym0506.routecontract:routecontract-core"))
            .using(project(":routecontract-core"))
        substitute(module("io.github.ym0506.routecontract:routecontract-shardingsphere-5.5"))
            .using(project(":routecontract-shardingsphere-5.5"))
        substitute(module("io.github.ym0506.routecontract:routecontract-shardingsphere-5.5.2"))
            .using(project(":routecontract-shardingsphere-5.5.2"))
    }
}
