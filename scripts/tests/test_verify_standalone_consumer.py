from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
VERIFIER = ROOT / "scripts" / "verify-standalone-consumer.sh"
BUILD = ROOT / "examples" / "standalone-consumer" / "build.gradle"
MYSQL_TEST = (
    ROOT
    / "examples"
    / "standalone-consumer"
    / "src"
    / "test"
    / "java"
    / "io"
    / "github"
    / "ym0506"
    / "routecontract"
    / "consumer"
    / "PublishedArtifactMySqlTest.java"
)
METADATA = (
    ROOT
    / "examples"
    / "standalone-consumer"
    / "gradle"
    / "verification-metadata.xml"
)


class VerifyStandaloneConsumerTest(unittest.TestCase):
    def test_split_publication_is_complete_before_consumer_resolution(self) -> None:
        verifier = VERIFIER.read_text(encoding="utf-8")
        self.assertIn(":routecontract-core:publishToMavenLocal", verifier)
        self.assertIn(":routecontract-shardingsphere-5.5:publishToMavenLocal", verifier)
        for required in (
            "published_core_artifact=",
            "published_core_pom=",
            "published_artifact=",
            "published_pom=",
            "Published RouteContract core and adapter coordinates are incomplete",
        ):
            self.assertIn(required, verifier)

    def test_dynamic_first_party_split_is_bounded_to_two_reviewed_modules(self) -> None:
        build = BUILD.read_text(encoding="utf-8")
        metadata = METADATA.read_text(encoding="utf-8")
        for module in (
            "routecontract-core",
            "routecontract-shardingsphere-5.5",
        ):
            self.assertIn(
                f'ignoredDependencies.add("${{routeContractGroup}}:{module}")',
                build,
            )
            self.assertIn(f'name="^{module.replace(".", "[.]")}$"', metadata)
        self.assertNotIn('name="^routecontract-.*$"', metadata)
        self.assertIn("systemProperty 'routecontract.coreJarName'", build)
        self.assertIn("systemProperty 'routecontract.adapterJarName'", build)
        self.assertNotIn("systemProperty 'routecontract.artifactJarName'", build)

    def test_mysql_probe_names_the_exact_553_split_provider(self) -> None:
        source = MYSQL_TEST.read_text(encoding="utf-8")
        self.assertIn(
            '"io.github.ym0506.routecontract.shardingsphere553.internal."',
            source,
        )
        self.assertIn('"RouteContract553SqlExecutionHook"', source)
        self.assertNotIn(
            '"io.github.ym0506.routecontract.internal.RouteContractSqlExecutionHook"',
            source,
        )


if __name__ == "__main__":
    unittest.main()
