import io.github.ym0506.routecontract.*;import io.github.ym0506.routecontract.manifest.*;import java.util.*;
public class ExplicitIdentityProbe {
 public static void main(String[] args) throws Exception {
  ManifestAttempt attempt=new ManifestAttempt("shard-a","a".repeat(64),1,List.of("java.lang.Long"),AttemptOutcome.CALLBACK_RETURNED,1);
  ManifestCounts counts=new ManifestCounts(1,1,0,0,1);ManifestPolicy policy=ManifestPolicy.strict(1,1);
  ObservedExecutionManifest a=new ObservedExecutionManifest(2,ShardingSphereRuntimeIdentity.SHARDINGSPHERE_5_5_3,"migration.operation",CaptureStatus.COMPLETE,policy,counts,List.of(attempt));
  ObservedExecutionManifest b=new ObservedExecutionManifest(2,ShardingSphereRuntimeIdentity.SHARDINGSPHERE_5_5_2,"migration.operation",CaptureStatus.COMPLETE,policy,counts,List.of(attempt));
  ObservedExecutionManifest c=new ObservedExecutionManifest(1,"migration.operation",CaptureStatus.COMPLETE,policy,counts,List.of(attempt));
  PhysicalExecutionAttempt physical=new PhysicalExecutionAttempt("ds_1","a".repeat(64),1,List.of("java.lang.Long"),ThreadRole.TRUNK,AttemptOutcome.CALLBACK_RETURNED,null);
  RouteSnapshot snapshot=new RouteSnapshot(RouteSnapshot.CURRENT_SCHEMA_VERSION,ShardingSphereRuntimeIdentity.SHARDINGSPHERE_5_5_3,"migration.operation",CaptureStatus.COMPLETE,1,1,0,0,1,0,List.of("ds_1"),List.of(physical),List.of());
  if(snapshot.schemaVersion()!=2||!snapshot.runtimeIdentity().equals(ShardingSphereRuntimeIdentity.SHARDINGSPHERE_5_5_3))throw new AssertionError("explicit snapshot identity");
  if(!a.equals(new ManifestCodec().decode(new ManifestCodec().encode(a))))throw new AssertionError("schema-2 round trip");
  RouteSnapshot otherRuntime=new RouteSnapshot(2,ShardingSphereRuntimeIdentity.SHARDINGSPHERE_5_5_2,"migration.operation",CaptureStatus.COMPLETE,1,1,0,0,1,0,List.of("ds_1"),List.of(physical),List.of());
  RouteSnapshot legacy=new RouteSnapshot(1,"migration.operation",CaptureStatus.COMPLETE,1,1,0,0,1,0,List.of("ds_1"),List.of(physical),List.of());
  if(snapshot.equals(otherRuntime)||snapshot.equals(legacy))throw new AssertionError("snapshot identity/schema components ignored");
  if(a.equals(b)||a.equals(c))throw new AssertionError("record components ignored");
  ManifestAssertions.assertMatched(new ManifestVerifier().verify(c,a));
  System.out.println("identityDiffersEqualsFalse=true;schemaDiffersEqualsFalse=true;schema1Schema2VerifierMatch=true");
 }
}
