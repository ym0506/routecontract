import io.github.ym0506.routecontract.manifest.ManifestDiffCode;
public class MigratedEnumProbe {
 static String decision(ManifestDiffCode code) {
  return switch(code) {
   case UNSUPPORTED_RUNTIME_IDENTITY, RUNTIME_IDENTITY_MISMATCH -> "blocking";
   case MATCH -> "match";
   default -> "requires review";
  };
 }
 public static void main(String[] args) {
  if(!decision(ManifestDiffCode.UNSUPPORTED_RUNTIME_IDENTITY).equals("blocking")
    ||!decision(ManifestDiffCode.RUNTIME_IDENTITY_MISMATCH).equals("blocking"))throw new AssertionError("identity findings must block");
  System.out.println("ROUTECONTRACT_MIGRATED_ENUM_PASS RCM004=blocking RCM005=blocking");
 }
}
