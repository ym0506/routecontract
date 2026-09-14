import io.github.ym0506.routecontract.*;
import io.github.ym0506.routecontract.manifest.*;
import java.util.*;
import java.nio.file.*;
public class LegacyModelProbe {
  static void check(boolean ok,String name){if(!ok)throw new AssertionError(name);}
  public static void main(String[] args) throws Exception {
    if(args.length>1 && args[1].equals("manifest-constant")) {
      new ObservedExecutionManifest(ObservedExecutionManifest.CURRENT_SCHEMA_VERSION,"constant.operation",CaptureStatus.INCOMPLETE,ManifestPolicy.strict(1,1),new ManifestCounts(0,0,0,0,0),List.of());
      System.out.println("ROUTECONTRACT_LEGACY_MANIFEST_CONSTANT_PASS"); return;
    }
    PhysicalExecutionAttempt attempt=new PhysicalExecutionAttempt("orders_0","a".repeat(64),1,List.of("java.lang.Long"),ThreadRole.TRUNK,AttemptOutcome.CALLBACK_RETURNED,null);
    RouteSnapshot snapshot=new RouteSnapshot(RouteSnapshot.CURRENT_SCHEMA_VERSION,"migration.operation",CaptureStatus.COMPLETE,1,1,0,0,1,0,List.of("orders_0"),List.of(attempt),List.of());
    RouteSnapshot twinSnapshot=new RouteSnapshot(RouteSnapshot.CURRENT_SCHEMA_VERSION,snapshot.operationId(),snapshot.status(),1,1,0,0,1,0,List.of("orders_0"),List.of(attempt),List.of());
    check(snapshot.equals(twinSnapshot)&&snapshot.hashCode()==twinSnapshot.hashCode(),"equal legacy snapshot twins");
    RouteAssertions.assertThat(snapshot).hasCompleteCapture().hasExactlyObservedPhysicalAttempts(1).hasNoReportedExecutionFailures().observesExactlyDataSourceNames("orders_0");
    DataSourceAliases aliases=DataSourceAliases.of(Map.of("orders_0","shard-a"));
    ManifestPolicy policy=ManifestPolicy.strict(1,1);
    ObservedExecutionManifest generated=ObservedExecutionManifest.from(snapshot,aliases,policy);
    ObservedExecutionManifest legacy=new ObservedExecutionManifest(ObservedExecutionManifest.CURRENT_SCHEMA_VERSION,snapshot.operationId(),snapshot.status(),policy,generated.counts(),generated.attempts());
    ObservedExecutionManifest twin=new ObservedExecutionManifest(ObservedExecutionManifest.CURRENT_SCHEMA_VERSION,snapshot.operationId(),snapshot.status(),policy,generated.counts(),generated.attempts());
    check(legacy.equals(twin)&&legacy.hashCode()==twin.hashCode(),"equal legacy twins");
    ManifestAssertions.assertMatched(new ManifestVerifier().verify(legacy,snapshot,aliases));
    ManifestAssertions.assertMatched(new ManifestVerifier().verify(legacy,generated));
    ManifestCodec codec=new ManifestCodec();
    check(legacy.equals(codec.decode(codec.encode(legacy))),"legacy JSON round trip");
    Path dir=Files.createTempDirectory(Path.of(args[0]),"manifest-");
    ManifestStore store=new ManifestStore(codec);
    Path candidate=store.writeCandidate(dir.resolve("approved.json"),dir.resolve("candidate.json"),legacy);
    check(legacy.equals(store.read(candidate)),"candidate storage round trip");
    System.out.println("ROUTECONTRACT_LEGACY_MODELS_PASS");
    System.out.println("snapshotComponents="+Arrays.toString(Arrays.stream(RouteSnapshot.class.getRecordComponents()).map(x->x.getName()+":"+x.getType().getName()).toArray()));
    System.out.println("manifestComponents="+Arrays.toString(Arrays.stream(ObservedExecutionManifest.class.getRecordComponents()).map(x->x.getName()+":"+x.getType().getName()).toArray()));
    System.out.println("snapshotStringHasIdentity="+snapshot.toString().contains("runtimeIdentity="));
    System.out.println("manifestStringHasIdentity="+legacy.toString().contains("runtimeIdentity="));
    Files.write(Path.of(args[0]).resolve("legacy-schema1.json"),codec.encode(legacy));
    System.out.println("snapshotCodeSource="+Path.of(RouteSnapshot.class.getProtectionDomain().getCodeSource().getLocation().toURI()).getFileName());
    System.out.println("generatedSchema="+generated.schemaVersion());
  }
}
